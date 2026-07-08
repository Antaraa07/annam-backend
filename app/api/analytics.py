from fastapi import APIRouter

from app.services import analytics_service

router = APIRouter()


@router.get("/analytics/summary")
def get_summary():
    return analytics_service.get_summary()


@router.get("/analytics/owners")
def owner_stats():
    return analytics_service.get_by_owner()


@router.get("/analytics/departments")
def department_stats():
    return analytics_service.get_by_department()


@router.get("/analytics/recent-uploads")
def recent_uploads(limit: int = 5):
    return analytics_service.get_recent(limit)


@router.get("/analytics/active-users")
def active_users(window_days: int = 7, top_n: int = 5):
    # window_days isn't applied yet (no time-window filter in the SQL below) —
    # this just ranks all-time upload counts per owner for now.
    top = analytics_service.get_active_users(top_n)
    return {
        "active_users": len(top),
        "top": top,
    }