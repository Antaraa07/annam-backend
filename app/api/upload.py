from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.services.auth_service import get_user
from app.services.upload_service import save_file

router = APIRouter()


@router.post("/upload")
async def upload_image(
    username: str = Form(...),
    dataset_name: str = Form(...),
    owner: str = Form(...),
    lab_dept: str = Form(...),
    version: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...)
):

    user = get_user(username)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if user["role"] not in ["admin", "researcher"]:
        raise HTTPException(
            status_code=403,
            detail="Permission denied"
        )

    metadata = {
        "dataset_name": dataset_name,
        "owner": owner,
        "lab/dept": lab_dept,
        "version": version,
        "description": description
    }

    result = save_file(file, metadata)

    return {
        "image_id": result["image_id"],
        "filename": result["filename"],
        "status": "uploaded"
    }