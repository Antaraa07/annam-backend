from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path
from app.services.s3_service import is_s3_enabled, get_s3_object_stream

router = APIRouter()

UPLOAD_DIR = Path("storage/uploads")


@router.get("/image/{filename}")
def get_image(filename: str):
    from app.db import run_one
    row = run_one("SELECT path FROM datasets WHERE filename = ? LIMIT 1", [filename])
    if row:
        path_str = row[0]
        if path_str.startswith("s3://"):
            key = "/".join(path_str.split("/")[3:])
            stream = get_s3_object_stream(key)
            if stream:
                media_type = "image/jpeg"
                if filename.lower().endswith(".png"):
                    media_type = "image/png"
                elif filename.lower().endswith(".gif"):
                    media_type = "image/gif"
                elif filename.lower().endswith(".webp"):
                    media_type = "image/webp"
                elif filename.lower().endswith(".json"):
                    media_type = "application/json"
                return StreamingResponse(stream, media_type=media_type)
        else:
            local_path = Path(path_str)
            if local_path.exists():
                return FileResponse(local_path)

    image_path = UPLOAD_DIR / filename
    if image_path.exists():
        return FileResponse(image_path)

    if is_s3_enabled():
        stream = get_s3_object_stream(f"uploads/{filename}")
        if stream:
            media_type = "image/jpeg"
            if filename.lower().endswith(".png"):
                media_type = "image/png"
            elif filename.lower().endswith(".gif"):
                media_type = "image/gif"
            elif filename.lower().endswith(".webp"):
                media_type = "image/webp"
            return StreamingResponse(stream, media_type=media_type)

    return FileResponse(image_path)
