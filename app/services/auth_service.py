import hashlib
import json
from pathlib import Path

USERS_FILE = Path(__file__).resolve().parent.parent.parent / "storage" / "users" / "users.json"


def _load() -> list:
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def _save(users: list):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def _hash(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def get_user(username: str):
    for user in _load():
        if user["username"] == username:
            return user
    return None


def verify_user(username: str, password_plain: str):
    user = get_user(username)
    if not user:
        return None
    if user.get("password_hash") == _hash(password_plain):
        return user
    return None


def create_user(username: str, password_plain: str, role: str) -> bool:
    """Returns False if username already exists."""
    users = _load()
    if any(u["username"] == username for u in users):
        return False
    users.append({"username": username, "role": role, "password_hash": _hash(password_plain)})
    _save(users)
    return True


def delete_user(username: str) -> bool:
    """Returns False if user not found."""
    users = _load()
    new = [u for u in users if u["username"] != username]
    if len(new) == len(users):
        return False
    _save(new)
    return True


def update_role(username: str, new_role: str) -> bool:
    users = _load()
    for u in users:
        if u["username"] == username:
            u["role"] = new_role
            _save(users)
            return True
    return False


def change_password(username: str, current_plain: str, new_plain: str) -> bool:
    if not verify_user(username, current_plain):
        return False
    users = _load()
    for u in users:
        if u["username"] == username:
            u["password_hash"] = _hash(new_plain)
            break
    _save(users)
    return True