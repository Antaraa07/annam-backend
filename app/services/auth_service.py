from pathlib import Path
import json

USERS_FILE = Path("storage/users/users.json")


def get_user(username: str):

    with open(USERS_FILE, "r") as f:
        users = json.load(f)

    for user in users:
        if user["username"] == username:
            return user

    return None