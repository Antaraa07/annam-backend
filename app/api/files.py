from fastapi import APIRouter
from pathlib import Path

router = APIRouter()

UPLOAD_DIR = Path("storage/uploads")

@router.get("/files")
def list_files():

    files = []

    for file in UPLOAD_DIR.iterdir():
        files.append({
            "name": file.name,
            "size": file.stat().st_size
        })

    return files