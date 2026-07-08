from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.auth_service import get_user

router = APIRouter()

STORAGE_METADATA_DIR = Path("storage/metadata")
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
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_projects(projects: List[Dict[str, Any]]) -> None:
    STORAGE_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=2)


def _require_admin(user: Optional[Dict[str, Any]]):
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")


def _get_username(username: Optional[str]) -> str:
    if not username:
        raise HTTPException(status_code=401, detail="Username required")
    return username


class ProjectOut(BaseModel):
    project_id: str
    name: str
    description: str
    owner: str
    created_at: str
    label_classes: List[str] = []


class CreateProjectRequest(BaseModel):
    name: str
    description: str
    label_classes: Optional[List[str]] = []


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
            # frontend sends JSON.stringify([...])
            parsed = json.loads(label_classes)
            if isinstance(parsed, list):
                parsed_label_classes = [str(x) for x in parsed]
        except Exception:
            # if it isn't JSON, ignore
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
    }


    projects.append(project)
    _save_projects(projects)
    return project


@router.get("/projects", response_model=List[ProjectOut])
def list_projects(username: str):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    return [p for p in projects if p.get("owner") == username]


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, username: str):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    for p in projects:
        if p.get("project_id") == project_id and p.get("owner") == username:
            return p

    raise HTTPException(status_code=404, detail="Project not found")


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, username: str):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    new_projects = [p for p in projects if not (p.get("project_id") == project_id and p.get("owner") == username)]

    if len(new_projects) == len(projects):
        raise HTTPException(status_code=404, detail="Project not found")

    _save_projects(new_projects)
    return {"message": "Project deleted", "project_id": project_id}


@router.get("/projects/{project_id}/stats")
def project_stats(project_id: str, username: str):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    project = next(
        (p for p in projects if p.get("project_id") == project_id and p.get("owner") == username),
        None,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    metadata_dir = STORAGE_METADATA_DIR
    total_images = 0
    recent_candidates: List[tuple[str, Dict[str, Any]]] = []

    for meta_file in metadata_dir.glob("*.json"):
        if meta_file.name == "projects.json":
            continue

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                md = json.load(f)
        except Exception:
            continue

        if md.get("project_id") != project_id:
            continue

        total_images += 1

        ts = md.get("timestamp")
        # Fallback to mtime if timestamp is absent/unparseable.
        if isinstance(ts, str) and ts.strip():
            sort_key = ts
        else:
            sort_key = (
                datetime.utcfromtimestamp(meta_file.stat().st_mtime)
                .replace(microsecond=0)
                .isoformat()
                + "Z"
            )

        recent_candidates.append((sort_key, md))

    recent_candidates.sort(key=lambda x: x[0], reverse=True)
    recent = [md for _, md in recent_candidates[:5]]

    return {
        "total_images": total_images,
        "recent_uploads": recent,
    }


@router.post("/projects/{project_id}/bulk-upload")
async def bulk_upload(
    project_id: str,
    files: List[UploadFile] = File(...),
    label: Optional[str] = Form(None),
    username: str = Form(...),
):
    user = get_user(username)
    _require_admin(user)

    projects = _load_projects()
    project = next(
        (p for p in projects if p.get("project_id") == project_id and p.get("owner") == username),
        None,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    upload_dir = Path("storage/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir = STORAGE_METADATA_DIR
    metadata_dir.mkdir(parents=True, exist_ok=True)

    uploaded_filenames: List[str] = []
    timestamp = _now_iso()

    for f in files:
        ext = f.filename.split(".")[-1].lower() if "." in f.filename else "jpg"
        image_id = str(uuid.uuid4())
        filename = f"{image_id}.{ext}"

        file_path = upload_dir / filename
        with open(file_path, "wb") as buffer:
            content = await f.read()
            buffer.write(content)

        metadata = {
            "image_id": image_id,
            "filename": filename,
            "project_id": project_id,
            "owner": username,
            "dataset_name": f"{project.get('name', '')} - {timestamp}",
            "lab/dept": "General",
            "version": "1.0",
            "description": f"Bulk uploaded with label: {label}" if label else "Bulk uploaded",
            "label": label,
            "timestamp": timestamp,
        }

        meta_path = metadata_dir / f"{image_id}.json"
        with open(meta_path, "w", encoding="utf-8") as meta_file:
            json.dump(metadata, meta_file, indent=4)

        uploaded_filenames.append(filename)

    return {
        "uploaded_count": len(uploaded_filenames),
        "files": uploaded_filenames,
    }

