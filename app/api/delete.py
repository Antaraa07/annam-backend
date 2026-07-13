from fastapi import APIRouter, HTTPException
from app.services.auth_service import get_user
from app.services.upload_service import delete_file

router = APIRouter()


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

    success = delete_file(image_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    return {
        "message": "Dataset deleted successfully",
        "image_id": image_id
    }