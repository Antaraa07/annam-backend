from __future__ import annotations

import json
import re
import uuid
import io
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.auth_service import get_user

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_METADATA_DIR = BASE_DIR / "storage" / "metadata"
PROJECTS_FILE = STORAGE_METADATA_DIR / "projects.json"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _load_projects() -> List[Dict[str, Any]]:
    STORAGE_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PROJECTS_FILE.exists():
        return []
    try:
        with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for p in data:
                if "status" not in p:
                    p["status"] = "not started"
            return data
        return []
    except Exception:
        return []


def _save_projects(projects: List[Dict[str, Any]]) -> None:
    STORAGE_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=2)


def _require_admin(user: Optional[Dict[str, Any]]):
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("role") not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Permission denied")


def _resolve_category(label: Optional[str], filename: Optional[str], label_classes: List[str]) -> str:
    """Resolve a human-readable category for a file.

    Priority:
    1. An explicit `label` value already stored/provided (e.g. from an annotation file).
    2. A match between the project's label_classes and the filename.
    3. If the project has exactly one label class, use it directly (covers the common
       case of a project dedicated to a single category, e.g. Cutworm -> "Pest").
    4. The first "word" of the filename, if it isn't purely numeric.
    5. "Unlabelled" as a last resort.

    This is the single source of truth for category resolution so that stored data
    (via bulk_upload) and computed stats (via project_stats) never disagree.
    """
    if label:
        return str(label).capitalize()

    if filename:
        name_lower = filename.lower()
        for lc in label_classes:
            if lc.lower() in name_lower:
                return lc.capitalize()

    if len(label_classes) == 1:
        return label_classes[0].capitalize()

    if filename:
        parts = re.split(r'[_\-\s.]', filename)
        first_word = parts[0] if parts else ""
        if first_word and not first_word.isdigit():
            return first_word.capitalize()

    return "Unlabelled"


class ProjectOut(BaseModel):
    project_id: str
    name: str
    description: str
    owner: str
    created_at: str
    label_classes: List[str] = []
    assigned_users: List[str] = []
    status: str = "not started"


@router.post("/projects", response_model=ProjectOut)
def create_project(
    name: str = Form(...),
    description: str = Form(...),
    label_classes: Optional[str] = Form(None),
    username: str = Form(...),
):
    user = get_user(username)
    _require_admin(user)

    parsed_label_classes: List[str] = []
    if label_classes:
        try:
            parsed = json.loads(label_classes)
            if isinstance(parsed, list):
                parsed_label_classes = [str(x) for x in parsed]
        except Exception:
            parsed_label_classes = []

    projects = _load_projects()
    project_id = str(uuid.uuid4())

    project = {
        "project_id": project_id,
        "name": name,
        "description": description,
        "owner": username,
        "created_at": _now_iso(),
        "label_classes": parsed_label_classes,
        "assigned_users": [],
        "status": "not started",
    }

    projects.append(project)
    _save_projects(projects)
    return project


@router.patch("/projects/{project_id}/status")
def update_project_status(project_id: str, status: str, username: str):
    user = get_user(username)
    _require_admin(user)

    if status not in {"not started", "ongoing", "completed"}:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'not started', 'ongoing', or 'completed'.")

    projects = _load_projects()
    for p in projects:
        if p.get("project_id") == project_id:
            p["status"] = status
            _save_projects(projects)
            return p

    raise HTTPException(status_code=404, detail="Project not found")


@router.get("/my-projects")
def list_assigned_projects(username: str):
    """Returns projects assigned to a non-admin user."""
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    projects = _load_projects()
    return [p for p in projects if username in p.get("assigned_users", [])]


@router.get("/projects", response_model=List[ProjectOut])
def list_projects(username: str):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    if user.get("role") == "superadmin":
        return projects
    return [p for p in projects if p.get("owner") == username]


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, username: str):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    for p in projects:
        if p.get("project_id") == project_id and (user.get("role") == "superadmin" or p.get("owner") == username):
            return p

    raise HTTPException(status_code=404, detail="Project not found")


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, username: str):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    new_projects = [p for p in projects if not (p.get("project_id") == project_id and (user.get("role") == "superadmin" or p.get("owner") == username))]

    if len(new_projects) == len(projects):
        raise HTTPException(status_code=404, detail="Project not found")

    _save_projects(new_projects)

    # Clean up associated datasets from DuckDB
    from app.db import run_execute
    run_execute("DELETE FROM datasets WHERE project_id = ?", [project_id])

    # Clean up local project files
    import shutil
    project_dir = BASE_DIR / "storage" / "uploads" / "projects" / project_id
    if project_dir.exists():
        try:
            shutil.rmtree(project_dir)
        except Exception:
            pass

    return {"message": "Project deleted", "project_id": project_id}


@router.post("/projects/{project_id}/assign")
def assign_user(project_id: str, username: str, assign_username: str):
    user = get_user(username)
    _require_admin(user)

    target = get_user(assign_username)
    if not target:
        raise HTTPException(status_code=404, detail="User to assign not found")

    projects = _load_projects()
    for p in projects:
        if p.get("project_id") == project_id and (user.get("role") == "superadmin" or p.get("owner") == username):
            assigned = p.setdefault("assigned_users", [])
            if assign_username not in assigned:
                assigned.append(assign_username)
            _save_projects(projects)
            return {"message": f"{assign_username} assigned to project"}

    raise HTTPException(status_code=404, detail="Project not found")


@router.delete("/projects/{project_id}/assign")
def unassign_user(project_id: str, username: str, assign_username: str):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    for p in projects:
        if p.get("project_id") == project_id and (user.get("role") == "superadmin" or p.get("owner") == username):
            assigned = p.get("assigned_users", [])
            if assign_username not in assigned:
                raise HTTPException(status_code=404, detail="User not assigned to this project")
            p["assigned_users"] = [u for u in assigned if u != assign_username]
            _save_projects(projects)
            return {"message": f"{assign_username} removed from project"}

    raise HTTPException(status_code=404, detail="Project not found")


@router.get("/projects/{project_id}/stats")
def project_stats(project_id: str, username: str):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    projects = _load_projects()
    project = next((p for p in projects if p.get("project_id") == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    is_admin = user.get("role") == "superadmin" or (user.get("role") == "admin" and project.get("owner") == username)
    is_assigned = username in project.get("assigned_users", [])
    if not is_admin and not is_assigned:
        raise HTTPException(status_code=403, detail="Not authorized")

    from app.db import run, run_one
    from app.api.datasets import _row_to_dataset

    total_count_row = run_one("SELECT count(*) FROM datasets WHERE project_id = ?", [project_id])
    total_images = total_count_row[0] if total_count_row else 0

    recent_rows = run("SELECT * FROM datasets WHERE project_id = ? ORDER BY uploaded_at DESC LIMIT 50", [project_id])
    recent_uploads = [_row_to_dataset(r) for r in recent_rows]

    # Calculate label counts across all files in the project
    label_rows = run("SELECT label, filename FROM datasets WHERE project_id = ?", [project_id])
    label_classes = project.get("label_classes", [])
    label_counts = {}

    for r in label_rows:
        resolved_cap = _resolve_category(r.get("label"), r.get("filename"), label_classes)
        label_counts[resolved_cap] = label_counts.get(resolved_cap, 0) + 1

    return {
        "total_images": total_images,
        "recent_uploads": recent_uploads,
        "label_counts": label_counts,
    }


@router.post("/projects/{project_id}/bulk-upload")
async def bulk_upload(
    project_id: str,
    files: List[UploadFile] = File(...),
    label: Optional[str] = Form(None),
    username: str = Form(...),
    csv_file: Optional[UploadFile] = File(None),
):
    """
    Project bulk upload (annotated data).

    Mirrors the raw-upload flow in upload_service.py.save_file(): every
    uploaded image gets one row in the `datasets` table, with `path` stored
    as "s3://<bucket>/<key>" so project_stats(), get_project_images(), and
    bulk_download() keep working unmodified.

    The only differences from the raw upload:
      - The actual S3 upload (image + LabelMe JSON) is done by
        save_annotation_file() in annotation_service.py, which writes to
          <ProjectDataset>/<Version>/images/<uuid>.jpg
          <ProjectDataset>/<Version>/annotations/<uuid>.json
        bulk_upload() takes the image_key it returns and builds the same
        "s3://bucket/key" path string that save_file() builds.
      - Images and their LabelMe JSON are paired by basename
        (e.g. "abc.jpg" <-> "abc.json"), same convention as upload.py.
      - The annotation's json_key is stored inside metadata_json (no new
        column, no schema change) so it can be recovered later for
        extraction/download.
    """
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    projects = _load_projects()
    project = next((p for p in projects if p.get("project_id") == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    is_admin = user.get("role") == "superadmin" or (user.get("role") == "admin" and project.get("owner") == username)
    is_assigned = username in project.get("assigned_users", [])
    if not is_admin and not is_assigned:
        raise HTTPException(status_code=403, detail="Not authorized to upload to this project")

    from app.services.annotation_service import save_annotation_file
    from app.services.s3_service import get_project_bucket_name
    from app.db import run_execute

    label_classes = project.get("label_classes", [])
    timestamp = _now_iso()
    version = "1.0"  # project model has no version field today; revisit if/when one is added
    dataset_name = project.get("name", "Project")
    bucket_name = get_project_bucket_name()

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

    # Separate images from JSON annotations, matched by basename
    # e.g. "abc.jpg" pairs with "abc.json"
    images_by_stem: Dict[str, UploadFile] = {}
    annotations_by_stem: Dict[str, Dict[str, Any]] = {}

    for f in files:
        stem = Path(f.filename).stem
        suffix = Path(f.filename).suffix.lower()

        if suffix == ".json":
            raw = await f.read()
            try:
                annotations_by_stem[stem] = json.loads(raw)
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid JSON annotation file: {f.filename}",
                )
        elif suffix in IMAGE_EXTS:
            images_by_stem[stem] = f
        # anything else (e.g. a stray csv) is ignored here

    if not images_by_stem:
        raise HTTPException(status_code=400, detail="No image files found in upload")

    uploaded_filenames: List[str] = []
    results: List[Dict[str, Any]] = []

    for stem, image_file in images_by_stem.items():
        safe_filename = Path(image_file.filename).name
        annotation_json = annotations_by_stem.get(stem)

        resolved_department = _resolve_category(label, safe_filename, label_classes)

        metadata = {
            "project_id": project_id,
            "project_name": project.get("name", "Project"),
            "dataset_name": dataset_name,
            "owner": username,
            "label": label,
            "department": resolved_department,
            "version": version,
            "uploaded_at": timestamp,
        }

        if annotation_json is None:
            print(f"WARNING: No matching annotation JSON for {safe_filename}, uploading image only")

        result = save_annotation_file(
            image_file=image_file,
            annotation_json=annotation_json,
            metadata=metadata,
        )
        # result = {"filename": ..., "image_key": ..., "json_key": ... or None}

        image_id = str(uuid.uuid4())
        stored_path = f"s3://{bucket_name}/{result['image_key']}"

        # Preserve everything passed into save_annotation_file() (not just
        # the S3 keys), same as save_file()'s "known columns vs. extra"
        # split, so metadata_json carries the full picture, not a subset.
        extra = {
            **metadata,
            "image_key": result.get("image_key"),
            "json_key": result.get("json_key"),
        }

        run_execute(
            """
            INSERT INTO datasets
                (
                    image_id,
                    filename,
                    path,
                    dataset_name,
                    owner,
                    department,
                    version,
                    project_id,
                    label,
                    metadata_json
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                image_id,
                safe_filename,
                stored_path,
                dataset_name,
                username,
                resolved_department,
                version,
                project_id,
                label,
                json.dumps(extra),
            ],
        )

        results.append(result)
        uploaded_filenames.append(safe_filename)

    return {
        "uploaded_count": len(uploaded_filenames),
        "files": uploaded_filenames,
        "results": results,
    }


@router.get("/projects/{project_id}/images")
def get_project_images(
    project_id: str,
    username: str,
    page: Optional[int] = Query(None),
    limit: Optional[int] = Query(None),
):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    projects = _load_projects()
    project = next((p for p in projects if p.get("project_id") == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    is_admin = user.get("role") == "superadmin" or (user.get("role") == "admin" and project.get("owner") == username)
    is_assigned = username in project.get("assigned_users", [])
    if not is_admin and not is_assigned:
        raise HTTPException(status_code=403, detail="Not authorized")

    from app.db import run
    from app.api.datasets import _row_to_dataset

    if page is not None and limit is not None:
        offset = (page - 1) * limit
        rows = run(
            "SELECT * FROM datasets WHERE project_id = ? ORDER BY uploaded_at DESC LIMIT ? OFFSET ?",
            [project_id, limit, offset]
        )
    else:
        rows = run("SELECT * FROM datasets WHERE project_id = ? ORDER BY uploaded_at DESC", [project_id])
    return [_row_to_dataset(r) for r in rows]


@router.get("/projects/{project_id}/bulk-download")
def bulk_download(project_id: str, username: str):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    projects = _load_projects()
    project = next((p for p in projects if p.get("project_id") == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    is_admin = user.get("role") == "superadmin" or (user.get("role") == "admin" and project.get("owner") == username)
    is_assigned = username in project.get("assigned_users", [])
    if not is_admin and not is_assigned:
        raise HTTPException(status_code=403, detail="Not authorized to download this project data")

    from app.db import run
    rows = run("SELECT path, filename, metadata_json FROM datasets WHERE project_id = ?", [project_id])
    if not rows:
        raise HTTPException(status_code=404, detail="No files found for this project")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for r in rows:
            path_str = r["path"]
            filename = r["filename"]
            metadata_json = r.get("metadata_json")

            # 1. Fetch and write image
            image_content = None
            if path_str.startswith("s3://"):
                from app.services.s3_service import get_s3_object_stream, get_project_bucket_name
                key = "/".join(path_str.split("/")[3:])
                bucket_name = get_project_bucket_name()
                stream = get_s3_object_stream(key, bucket=bucket_name)
                if not stream:
                    # Fallback to the bucket in the URI
                    uri_bucket = path_str.split("/")[2]
                    if uri_bucket != bucket_name:
                        stream = get_s3_object_stream(key, bucket=uri_bucket)
                if stream:
                    image_content = stream.read()
            else:
                local_path = Path(path_str)
                if local_path.exists():
                    with open(local_path, "rb") as lf:
                        image_content = lf.read()

            if image_content:
                zip_file.writestr(f"images/{filename}", image_content)

            # 2. Fetch and write JSON annotation
            if metadata_json:
                try:
                    meta = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                    json_key = meta.get("json_key")
                    if json_key:
                        json_filename = Path(json_key).name
                        json_content = None
                        if path_str.startswith("s3://"):
                            from app.services.s3_service import get_s3_object_stream, get_project_bucket_name
                            bucket_name = get_project_bucket_name()
                            stream = get_s3_object_stream(json_key, bucket=bucket_name)
                            if not stream:
                                uri_bucket = path_str.split("/")[2]
                                if uri_bucket != bucket_name:
                                    stream = get_s3_object_stream(json_key, bucket=uri_bucket)
                            if stream:
                                json_content = stream.read()
                        else:
                            local_json_path = Path(path_str).parent.parent / "annotations" / f"{Path(path_str).stem}.json"
                            if local_json_path.exists():
                                with open(local_json_path, "rb") as lf:
                                    json_content = lf.read()

                        if json_content:
                            zip_file.writestr(f"annotations/{json_filename}", json_content)
                except Exception as e:
                    print(f"Error zipping json for {filename}: {e}")

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=project_{project_id}.zip"}
    )


@router.post("/projects/clean-orphans")
def clean_orphans(username: str):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.get("role") not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    projects = _load_projects()
    valid_ids = {p.get("project_id") for p in projects if p.get("project_id")}

    from app.db import run, run_execute
    db_project_ids = run("SELECT DISTINCT project_id FROM datasets WHERE project_id IS NOT NULL")
    cleaned_count = 0

    for row in db_project_ids:
        pid = row.get("project_id")
        if pid and pid not in valid_ids:
            from app.db import run_one
            count_row = run_one("SELECT count(*) FROM datasets WHERE project_id = ?", [pid])
            count = count_row[0] if count_row else 0
            cleaned_count += count

            run_execute("DELETE FROM datasets WHERE project_id = ?", [pid])
            
            import shutil
            project_dir = BASE_DIR / "storage" / "uploads" / "projects" / pid
            if project_dir.exists():
                try:
                    shutil.rmtree(project_dir)
                except Exception:
                    pass

    return {
        "message": "Orphaned datasets cleaned up",
        "cleaned_count": cleaned_count
    }