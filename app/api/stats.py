from fastapi import APIRouter, HTTPException
from pathlib import Path

from app.services.auth_service import get_user

router = APIRouter()

UPLOAD_DIR = Path("storage/uploads")
METADATA_DIR = Path("storage/metadata")


@router.get("/stats")
def get_stats(username: str):

    user = get_user(username)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if user["role"] not in ["superadmin", "admin", "researcher"]:
        raise HTTPException(
            status_code=403,
            detail="Permission denied"
        )

    files = list(UPLOAD_DIR.glob("*"))
    metadata_files = list(METADATA_DIR.glob("*.json"))

    total_storage = sum(
        file.stat().st_size
        for file in files
    )

    return {
        "total_datasets": len(metadata_files),
        "total_files": len(files),
        "total_storage_bytes": total_storage
    }
