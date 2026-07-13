import uuid
import shutil
import json
from pathlib import Path

from app.db import run_execute, run_one
from app.services.s3_service import is_s3_enabled, upload_file_to_s3, delete_file_from_s3, get_bucket_name

UPLOAD_DIR = Path("storage/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_file(file, metadata: dict):
    """
    Saves the uploaded file (either to S3 if configured, or local storage)
    and writes its metadata as a row in DuckDB.
    """

    image_id = str(uuid.uuid4())
    extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{image_id}.{extension}"
    file_path = UPLOAD_DIR / filename

    # Save locally as temp first
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    stored_path = str(file_path)
    if is_s3_enabled():
        s3_key = f"uploads/{filename}"
        if upload_file_to_s3(file_path, s3_key):
            stored_path = f"s3://{get_bucket_name()}/{s3_key}"
            # Delete local temp file
            try:
                file_path.unlink()
            except Exception:
                pass

    dataset_name = metadata.get("dataset_name")
    owner = metadata.get("owner")
    department = metadata.get("department") or metadata.get("lab/dept")
    version = metadata.get("version")
    project_id = metadata.get("project_id")
    label = metadata.get("label")

    known_keys = ("dataset_name", "owner", "department", "lab/dept", "version", "project_id", "label")
    extra = {k: v for k, v in metadata.items() if k not in known_keys}

    run_execute(
        """
        INSERT INTO datasets
            (image_id, filename, path, dataset_name, owner, department, version, project_id, label, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            image_id,
            filename,
            stored_path,
            dataset_name,
            owner,
            department,
            version,
            project_id,
            label,
            json.dumps(extra),
        ],
    )

    return {
        "image_id": image_id,
        "filename": filename,
        "path": stored_path,
    }


def delete_file(image_id: str):
    """Removes a dataset's file from S3 or local disk and its row from DuckDB."""
    row = run_one("SELECT path FROM datasets WHERE image_id = ?", [image_id])

    if row is None:
        return False

    path_str = row[0]
    if path_str.startswith("s3://"):
        # e.g. s3://bucket/uploads/filename
        key = "/".join(path_str.split("/")[3:])
        delete_file_from_s3(key)
    else:
        file_path = Path(path_str)
        if file_path.exists():
            file_path.unlink()

    run_execute("DELETE FROM datasets WHERE image_id = ?", [image_id])
    return True