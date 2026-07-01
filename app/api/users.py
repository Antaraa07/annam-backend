from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter()

USERS_FILE = Path("storage/users/users.json")


@router.get("/users")
def list_users():

    with open(USERS_FILE, "r") as f:
        users = json.load(f)

    return users