from __future__ import annotations

import json
import uuid
import io
import zipfile
from datetime import datetime
from pathlib import Path
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
    import re

    total_count_row = run_one("SELECT count(*) FROM datasets WHERE project_id = ?", [project_id])
    total_images = total_count_row[0] if total_count_row else 0

    recent_rows = run("SELECT * FROM datasets WHERE project_id = ? ORDER BY uploaded_at DESC LIMIT 50", [project_id])
    recent_uploads = [_row_to_dataset(r) for r in recent_rows]

    # Calculate label counts across all files in the project
    label_rows = run("SELECT label, filename FROM datasets WHERE project_id = ?", [project_id])
    label_classes = project.get("label_classes", [])
    label_counts = {}

    for r in label_rows:
        lbl = r.get("label")
        filename = r.get("filename")
        if lbl:
            resolved = lbl
        else:
            resolved = "Unlabelled"
            if filename:
                name_lower = filename.lower()
                for lc in label_classes:
                    if lc.lower() in name_lower:
                        resolved = lc
                        break
                if resolved == "Unlabelled":
                    parts = re.split(r'[_\-\s.]', filename)
                    first_word = parts[0] if parts else ""
                    if first_word and not first_word.isdigit():
                        resolved = first_word

        resolved_cap = resolved.capitalize() if resolved else "Unlabelled"
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

    import shutil
    from app.services.s3_service import is_s3_enabled, upload_file_to_s3, get_bucket_name
    from app.db import run_execute

    project_dir = BASE_DIR / "storage" / "uploads" / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    uploaded_filenames: List[str] = []
    timestamp = _now_iso()

    for f in files:
        safe_filename = Path(f.filename).name
        file_path = project_dir / safe_filename

        # Save locally first
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(f.file, buffer)

        stored_path = str(file_path)
        if is_s3_enabled():
            s3_key = f"uploads/projects/{project_id}/{safe_filename}"
            if upload_file_to_s3(file_path, s3_key):
                stored_path = f"s3://{get_bucket_name()}/{s3_key}"
                try:
                    file_path.unlink()
                except Exception:
                    pass

        image_id = str(uuid.uuid4())

        run_execute(
            """
            INSERT INTO datasets
                (image_id, filename, path, dataset_name, owner, department, version, project_id, label, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                image_id,
                safe_filename,
                stored_path,
                f"{project.get('name', 'Project')} - {timestamp}",
                username,
                "General",
                "1.0",
                project_id,
                None,
                "{}",
            ]
        )
        uploaded_filenames.append(safe_filename)

    return {
        "uploaded_count": len(uploaded_filenames),
        "files": uploaded_filenames,
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
    rows = run("SELECT path, filename FROM datasets WHERE project_id = ?", [project_id])
    if not rows:
        raise HTTPException(status_code=404, detail="No files found for this project")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for r in rows:
            path_str = r["path"]
            filename = r["filename"]
            content = None
            if path_str.startswith("s3://"):
                from app.services.s3_service import get_s3_object_stream
                key = "/".join(path_str.split("/")[3:])
                stream = get_s3_object_stream(key)
                if stream:
                    content = stream.read()
            else:
                local_path = Path(path_str)
                if local_path.exists():
                    with open(local_path, "rb") as lf:
                        content = lf.read()
            if content:
                zip_file.writestr(filename, content)

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
