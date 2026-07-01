from fastapi import APIRouter, HTTPException

from pathlib import Path
import json

from app.services.auth_service import get_user

router = APIRouter()

METADATA_DIR = Path("storage/metadata")
UPLOAD_DIR = Path("storage/uploads")


@router.delete("/dataset/{image_id}")
def delete_dataset(
    image_id: str,
    username: str
):

    user = get_user(username)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only admin can delete datasets"
        )

    metadata_file = METADATA_DIR / f"{image_id}.json"

    if not metadata_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    with open(metadata_file, "r") as f:
        metadata = json.load(f)

    filename = metadata["filename"]

    image_file = UPLOAD_DIR / filename

    if image_file.exists():
        image_file.unlink()

    metadata_file.unlink()

    return {
        "message": "Dataset deleted successfully",
        "image_id": image_id
    }