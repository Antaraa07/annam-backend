from fastapi import APIRouter, Query
from typing import Optional
from app.services import analytics_service

router = APIRouter()


@router.get("/analytics/summary")
def get_summary(username: Optional[str] = Query(None)):
    return analytics_service.get_summary(username)


@router.get("/analytics/owners")
def owner_stats():
    return analytics_service.get_by_owner()


@router.get("/analytics/departments")
def department_stats(username: Optional[str] = Query(None)):
    return analytics_service.get_by_department(username)


@router.get("/analytics/recent-uploads")
def recent_uploads(limit: int = 5, username: Optional[str] = Query(None)):
    return analytics_service.get_recent(limit, username)


@router.get("/analytics/active-users")
def active_users(window_days: int = 7, top_n: int = 5):
    top = analytics_service.get_active_users(top_n)
    return {
        "active_users": len(top),
        "top": top,
    }
