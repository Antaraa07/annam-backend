import uuid
import shutil
import json
from pathlib import Path

from app.db import run_execute, run_one

UPLOAD_DIR = Path("storage/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_file(file, metadata: dict):
    """
    Saves the uploaded file to disk (unchanged) and writes its metadata
    as a row in DuckDB (replaces the old storage/metadata/*.json file).

    The upload route (app/api/upload.py) sends department under the key
    "lab/dept", not "department" — we accept both here so this keeps
    working regardless of which key naming is used upstream.

    Anything not recognized as a named column falls into `metadata_json`
    so nothing submitted by the upload form is silently dropped.
    """

    image_id = str(uuid.uuid4())
    extension = file.filename.split(".")[-1]
    filename = f"{image_id}.{extension}"
    file_path = UPLOAD_DIR / filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    dataset_name = metadata.get("dataset_name")
    owner = metadata.get("owner")
    department = metadata.get("department") or metadata.get("lab/dept")
    version = metadata.get("version")

    known_keys = ("dataset_name", "owner", "department", "lab/dept", "version")
    extra = {k: v for k, v in metadata.items() if k not in known_keys}

    run_execute(
        """
        INSERT INTO datasets
            (image_id, filename, path, dataset_name, owner, department, version, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            image_id,
            filename,
            str(file_path),
            dataset_name,
            owner,
            department,
            version,
            json.dumps(extra),
        ],
    )

    return {
        "image_id": image_id,
        "filename": filename,
        "path": str(file_path),
    }


def delete_file(image_id: str):
    """Removes a dataset's file from disk and its row from DuckDB."""
    row = run_one("SELECT path FROM datasets WHERE image_id = ?", [image_id])

    if row is None:
        return False

    file_path = Path(row[0])
    if file_path.exists():
        file_path.unlink()

    run_execute("DELETE FROM datasets WHERE image_id = ?", [image_id])
    return True