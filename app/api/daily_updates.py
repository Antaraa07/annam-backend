import uuid
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import run, run_execute
from app.services.auth_service import get_user

router = APIRouter()
VALID_STATUSES = {"planned", "in_progress", "blocked", "done"}


class DailyUpdateRequest(BaseModel):
    username: str
    work_date: date
    project: str = ""
    work_done: str = Field(min_length=1, max_length=4000)
    status: str = "in_progress"
    next_steps: str = ""


@router.get("/daily-updates")
def list_daily_updates(username: str | None = None):
    query = """
        SELECT update_id, username, work_date, project, work_done, status, next_steps, created_at
        FROM daily_updates
    """
    params = []
    if username:
        query += " WHERE username = ?"
        params.append(username)
    query += " ORDER BY work_date DESC, created_at DESC"
    return run(query, params)


@router.post("/daily-updates", status_code=201)
def create_daily_update(update: DailyUpdateRequest):
    if not get_user(update.username):
        raise HTTPException(status_code=404, detail="User not found")
    if update.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")

    update_id = str(uuid.uuid4())
    run_execute(
        """
        INSERT INTO daily_updates (update_id, username, work_date, project, work_done, status, next_steps)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [update_id, update.username, update.work_date, update.project, update.work_done, update.status, update.next_steps],
    )
    return {"update_id": update_id, "status": "created"}
