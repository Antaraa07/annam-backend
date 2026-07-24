import json
print(">>> upload.py loaded <<<")
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.services.auth_service import get_user
from app.services.upload_service import save_file
from app.services.annotation_service import save_annotation_file

router = APIRouter()

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


def _annotation_index(
    annotation_files: list[UploadFile],
    paths: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Read JSON annotation files and index them by image filename.
    """
    indexed: dict[str, dict[str, Any]] = {}

    for file, relative_path in zip(annotation_files, paths):
        try:
            data = json.loads(file.file.read())
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        finally:
            file.file.seek(0)

        base = PurePosixPath(relative_path).stem.lower()

        payload = {
            "annotation": data,
            "annotation_path": relative_path,
        }

        indexed[base] = payload

        if (
            isinstance(data, dict)
            and isinstance(data.get("imagePath"), str)
        ):
            indexed[
                PurePosixPath(data["imagePath"]).stem.lower()
            ] = payload

    return indexed


def _base_metadata(
    dataset_name: str,
    owner: str,
    lab_dept: str,
    version: str,
    description: str,
    image_metadata: dict,
) -> dict:

    return {
        **image_metadata,
        "dataset_name": dataset_name,
        "owner": owner,
        "lab/dept": lab_dept,
        "version": version,
        "description": description,
    }


@router.post("/upload")
async def upload_image(
    username: str = Form(...),
    dataset_name: str = Form(...),
    owner: str = Form(...),
    lab_dept: str = Form(...),
    version: str = Form(...),
    description: str = Form(""),
    metadata_json: str = Form("{}"),
    file: UploadFile = File(...),
):

    user = get_user(username)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if user["role"] not in [
        "superadmin",
        "admin",
        "researcher",
        "intern",
    ]:
        raise HTTPException(
            status_code=403,
            detail="Permission denied",
        )

    try:
        image_metadata = json.loads(metadata_json)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=422,
            detail="metadata_json must be a valid JSON object",
        )

    if not isinstance(image_metadata, dict):
        raise HTTPException(
            status_code=422,
            detail="metadata_json must be a JSON object",
        )

    metadata = _base_metadata(
        dataset_name,
        owner,
        lab_dept,
        version,
        description,
        image_metadata,
    )

    result = save_file(file, metadata)

    return {
        "image_id": result["image_id"],
        "filename": result["filename"],
        "status": "uploaded",
    }


@router.post("/upload/batch")
async def upload_annotated_folder(
    username: str = Form(...),
    dataset_name: str = Form(...),
    owner: str = Form(...),
    lab_dept: str = Form(...),
    version: str = Form(...),
    description: str = Form(""),
    metadata_json: str = Form("{}"),
    relative_paths_json: str = Form("[]"),
    files: list[UploadFile] = File(...),
):
    """
    Upload an annotated folder.

    Images are uploaded to the annotation S3 bucket.
    Matching JSON files are uploaded to the annotation S3 bucket.

    S3 structure:

    dataset/
        version/
            images/
            annotations/
    """

    user = get_user(username)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if user["role"] not in [
        "superadmin",
        "admin",
        "researcher",
        "intern",
    ]:
        raise HTTPException(
            status_code=403,
            detail="Permission denied",
        )

    try:
        image_metadata = json.loads(metadata_json)
        relative_paths = json.loads(relative_paths_json)

    except (TypeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=422,
            detail="Invalid batch metadata",
        )

    if (
        not isinstance(image_metadata, dict)
        or not isinstance(relative_paths, list)
        or len(relative_paths) != len(files)
    ):
        raise HTTPException(
            status_code=422,
            detail="Batch files and paths do not match",
        )

    paths = [
        str(path).replace("\\", "/")
        for path in relative_paths
    ]

    annotation_files = [
        file
        for file, path in zip(files, paths)
        if PurePosixPath(path).suffix.lower() == ".json"
    ]

    annotation_paths = [
        path
        for path in paths
        if PurePosixPath(path).suffix.lower() == ".json"
    ]

    annotations = _annotation_index(
        annotation_files,
        annotation_paths,
    )

    uploaded = []
    skipped = []

    base_metadata = _base_metadata(
        dataset_name,
        owner,
        lab_dept,
        version,
        description,
        image_metadata,
    )

    for file, relative_path in zip(files, paths):

        if (
            PurePosixPath(relative_path).suffix.lower()
            not in IMAGE_EXTENSIONS
        ):
            continue

        metadata = {
            **base_metadata,
            "source_path": relative_path,
        }

        match = annotations.get(
            PurePosixPath(relative_path).stem.lower()
        )

        if not match:
            skipped.append(relative_path)

        result = save_annotation_file(
            image_file=file,
            annotation_json=(
                match["annotation"]
                if match
                else None
            ),
            metadata=metadata,
        )

        uploaded.append(
            {
                "filename": result["filename"],
                "image_key": result["image_key"],
                "json_key": result["json_key"],
                "source_path": relative_path,
                "has_annotation": bool(match),
            }
        )

    if not uploaded:
        raise HTTPException(
            status_code=422,
            detail="No supported image files found in the selected folder",
        )

    return {
        "status": "uploaded",
        "uploaded": uploaded,
        "images_uploaded": len(uploaded),
        "annotations_matched": len(uploaded) - len(skipped),
        "unannotated_images": skipped,
    }