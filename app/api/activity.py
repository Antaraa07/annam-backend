from fastapi import APIRouter
from app.services.analytics_service import load_datasets

router = APIRouter()


@router.get("/analytics/recent")
def recent_activity():
    df = load_datasets()

    if df.empty:
        return []

    recent = df.tail(5).iloc[::-1]

    return recent.to_dict(orient="records")