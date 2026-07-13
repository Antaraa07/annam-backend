from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from collections import Counter
from datetime import datetime, timezone
from typing import Optional, List
import json
import io
import zipfile
import csv
from pathlib import Path
from app.db import run
from app.api.projects import _load_projects

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "uploads"

router = APIRouter()


def _row_to_dataset(row: dict) -> dict:
    meta = {}
    if row.get("metadata_json"):
        try:
            meta = json.loads(row["metadata_json"])
        except Exception:
            pass

    meta["image_id"] = row["image_id"]
    meta["filename"] = row["filename"]
    meta["path"] = row["path"]
    meta["dataset_name"] = row["dataset_name"]
    meta["owner"] = row["owner"]
    meta["department"] = row["department"]
    meta["lab/dept"] = row["department"]
    meta["version"] = row["version"]
    meta["project_id"] = row["project_id"]
    meta["label"] = row["label"]
    meta["timestamp"] = row["uploaded_at"].isoformat() if row.get("uploaded_at") else None
    return meta


@router.get("/datasets")
def list_datasets(username: Optional[str] = Query(None)):
    if username:
        rows = run("SELECT * FROM datasets WHERE owner = ? ORDER BY uploaded_at DESC", [username])
    else:
        rows = run("SELECT * FROM datasets ORDER BY uploaded_at DESC")

    # attach project names in one pass
    projects = _load_projects()
    project_name_map = {p["project_id"]: p["name"] for p in projects}

    result = []
    for r in rows:
        d = _row_to_dataset(r)
        d["project_name"] = project_name_map.get(r["project_id"]) if r.get("project_id") else None
        result.append(d)
    return result


@router.get("/dataset/{image_id}")
def get_dataset(image_id: str):
    rows = run("SELECT * FROM datasets WHERE image_id = ?", [image_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _row_to_dataset(rows[0])


# ---------------------------------------------------------------------------
# Structured download — grouped by label/category/owner/dataset_name
# ---------------------------------------------------------------------------

GROUP_BY_COLUMN = {
    "label":        "label",
    "category":     "department",
    "owner":        "owner",
    "dataset_name": "dataset_name",
}


class DownloadRequest(BaseModel):
    username:   Optional[str]       = None
    group_by:   str                 = "label"
    formats:    List[str]           = ["zip", "csv", "json", "readme"]
    category:   Optional[str]       = None
    label:      Optional[str]       = None
    owner:      Optional[str]       = None
    search:     Optional[str]       = None
    project_id: Optional[str]       = None
    source:     Optional[str]       = None  # "raw" | "annotated"


@router.post("/datasets/download/structured")
def download_structured(req: DownloadRequest):
    """Query DuckDB with active filters, group images into labelled subfolders,
    attach labels.csv / labels.json / README.txt, and stream a ZIP."""

    if req.group_by not in GROUP_BY_COLUMN:
        raise HTTPException(status_code=400, detail=f"group_by must be one of {list(GROUP_BY_COLUMN)}")

    # ── 1. Build parameterised WHERE clause ──────────────────────────────────
    conditions, params = [], []

    effective_owner = req.owner or req.username
    if effective_owner:
        conditions.append("owner = ?")
        params.append(effective_owner)
    if req.category:
        conditions.append("department = ?")
        params.append(req.category)
    if req.label:
        conditions.append("label = ?")
        params.append(req.label)
    if req.project_id:
        conditions.append("project_id = ?")
        params.append(req.project_id)
    if req.source == "raw":
        conditions.append("project_id IS NULL")
    elif req.source == "annotated":
        conditions.append("project_id IS NOT NULL")
    if req.search:
        conditions.append("(LOWER(dataset_name) LIKE ? OR LOWER(filename) LIKE ?)")
        params.extend([f"%{req.search.lower()}%", f"%{req.search.lower()}%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = run(
        f"SELECT image_id, filename, dataset_name, owner, department, label, "
        f"version, project_id, uploaded_at, metadata_json "
        f"FROM datasets {where} ORDER BY uploaded_at DESC",
        params,
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No matching datasets found")

    # ── 2. Build in-memory ZIP ───────────────────────────────────────────────
    group_col = GROUP_BY_COLUMN[req.group_by]
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # 2a. Images in labelled subfolders
        if "zip" in req.formats:
            for row in rows:
                file_path = UPLOAD_DIR / row["filename"]
                if not file_path.exists():
                    continue
                folder = str(row.get(group_col) or "unlabelled").strip() or "unlabelled"
                # sanitise folder name
                folder = "".join(c if c.isalnum() or c in " _-" else "_" for c in folder)
                zf.write(file_path, f"{folder}/{row['filename']}")

        # 2b. labels.csv
        if "csv" in req.formats:
            csv_buf = io.StringIO()
            fieldnames = ["filename", "dataset_name", "owner", "category",
                          "label", "version", "project_id", "timestamp"]
            writer = csv.DictWriter(csv_buf, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "filename":     row["filename"],
                    "dataset_name": row["dataset_name"] or "",
                    "owner":        row["owner"] or "",
                    "category":     row["department"] or "",
                    "label":        row["label"] or "",
                    "version":      row["version"] or "",
                    "project_id":   row["project_id"] or "",
                    "timestamp":    row["uploaded_at"].isoformat() if row.get("uploaded_at") else "",
                })
            zf.writestr("labels.csv", csv_buf.getvalue())

        # 2c. labels.json
        if "json" in req.formats:
            records = []
            for row in rows:
                extra = {}
                if row.get("metadata_json"):
                    try:
                        extra = json.loads(row["metadata_json"])
                    except Exception:
                        pass
                records.append({
                    "filename":     row["filename"],
                    "dataset_name": row["dataset_name"],
                    "owner":        row["owner"],
                    "category":     row["department"],
                    "label":        row["label"],
                    "version":      row["version"],
                    "project_id":   row["project_id"],
                    "timestamp":    row["uploaded_at"].isoformat() if row.get("uploaded_at") else None,
                    **extra,
                })
            zf.writestr("labels.json", json.dumps(records, indent=2))

        # 2d. README.txt
        if "readme" in req.formats:
            label_counts = Counter(
                str(row.get(group_col) or "unlabelled") for row in rows
            )
            timestamps = [
                row["uploaded_at"] for row in rows if row.get("uploaded_at")
            ]
            date_range = (
                f"{min(timestamps).date()} to {max(timestamps).date()}"
                if timestamps else "N/A"
            )
            lines = [
                f"Dataset Export",
                f"Generated : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                f"Total Images: {len(rows)}",
                f"Grouped By  : {req.group_by}",
                f"Date Range  : {date_range}",
                "",
                "Label Distribution:",
            ]
            for lbl, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
                lines.append(f"  {lbl:<20} {cnt} images")
            if req.category:   lines += ["", f"Filter — category : {req.category}"]
            if req.label:      lines += [f"Filter — label    : {req.label}"]
            if req.search:     lines += [f"Filter — search   : {req.search}"]
            zf.writestr("README.txt", "\n".join(lines))

    buf.seek(0)
    zip_name = f"annam_export_{req.group_by}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"},
    )