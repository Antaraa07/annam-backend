from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter()

UPLOAD_DIR = Path("storage/uploads")


@router.get("/image/{filename}")
def get_image(filename: str):
    image_path = UPLOAD_DIR / filename

    return FileResponse(image_path)