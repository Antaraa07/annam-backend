from fastapi import APIRouter
from app.services.analytics_service import load_datasets

router = APIRouter()


@router.get("/analytics/recent")
def recent_activity():
    df = load_datasets()

    if df.empty:
        return []

    recent = df.head(5)  # already ordered DESC by uploaded_at in load_datasets()

    out = []
    for _, row in recent.iterrows():
        out.append({
            "dataset_name": row.get("dataset_name") or row.get("filename") or "Untitled",
            "owner": row.get("owner") or "Unknown",
            "department": row.get("department") or "Unassigned",
            "version": row.get("version") or "v1",
        })
    return out