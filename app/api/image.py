from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path
from app.services.s3_service import is_s3_enabled, get_s3_object_stream

router = APIRouter()

UPLOAD_DIR = Path("storage/uploads")


@router.get("/image/{filename}")
def get_image(filename: str):
    from app.db import run_one
    from app.services.s3_service import get_bucket_name, get_project_bucket_name
    row = run_one("SELECT path, project_id FROM datasets WHERE filename = ? LIMIT 1", [filename])
    if row:
        path_str, project_id = row[0], row[1]
        if path_str.startswith("s3://"):
            key = "/".join(path_str.split("/")[3:])
            bucket_name = get_project_bucket_name() if project_id else get_bucket_name()
            stream = get_s3_object_stream(key, bucket=bucket_name)
            if not stream:
                # Fallback to the bucket in the URI
                uri_bucket = path_str.split("/")[2]
                if uri_bucket != bucket_name:
                    stream = get_s3_object_stream(key, bucket=uri_bucket)
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
