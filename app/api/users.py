from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.auth_service import create_user, delete_user, update_role, _load

router = APIRouter()

VALID_ROLES = {"superadmin", "admin", "researcher", "student", "intern"}


@router.get("/users")
def list_users():
    return [{"username": u["username"], "role": u["role"]} for u in _load()]


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str


@router.post("/users", status_code=201)
def add_user(req: CreateUserRequest):
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {sorted(VALID_ROLES)}")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if not req.username.strip():
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    ok = create_user(req.username.strip(), req.password, req.role)
    if not ok:
        raise HTTPException(status_code=409, detail=f"Username '{req.username}' already exists")
    return {"status": "created", "username": req.username, "role": req.role}


class UpdateRoleRequest(BaseModel):
    role: str


@router.patch("/users/{username}")
def change_role(username: str, req: UpdateRoleRequest):
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {sorted(VALID_ROLES)}")
    ok = update_role(username, req.role)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated", "username": username, "role": req.role}


@router.delete("/users/{username}")
def remove_user(username: str):
    ok = delete_user(username)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted", "username": username}
