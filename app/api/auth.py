from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.auth_service import verify_user, change_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(request: LoginRequest):
    user = verify_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    return {
        "status": "success",
        "username": user["username"],
        "role": user["role"]
    }


class ChangePasswordRequest(BaseModel):
    username: str
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password_route(request: ChangePasswordRequest):
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    ok = change_password(request.username, request.current_password, request.new_password)
    if not ok:
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    return {"status": "success"}
