from fastapi import APIRouter

import pandas as pd

from app.services.analytics_service import load_datasets

router = APIRouter()


def _bytes_to_human(num_bytes: float) -> str:
    if num_bytes >= 1_073_741_824:
        return f"{num_bytes / 1_073_741_824:.1f} GB"
    if num_bytes >= 1_048_576:
        return f"{num_bytes / 1_048_576:.1f} MB"
    return f"{num_bytes / 1024:.1f} KB"


def _get_created_ts(df):
    """Best-effort extraction of a timestamp column for ordering.

    We try common keys used by dataset metadata; if missing, returns None.
    """
    for col in ["created_at", "created", "timestamp", "upload_time", "uploaded_at"]:
        if col in df.columns:
            return col
    return None


@router.get("/analytics/summary")
def get_summary():
    df = load_datasets()

    if df.empty:
        return {
            "datasets": 0,
            "owners": 0,
            "departments": 0,
            "storage": "0 GB",
        }

    datasets = int(len(df))
    owners = int(df["owner"].nunique()) if "owner" in df.columns else 0
    departments = int(df["lab/dept"].nunique()) if "lab/dept" in df.columns else 0

    # Sum file sizes if column exists, else fallback
    if "size_bytes" in df.columns:
        total_bytes = float(df["size_bytes"].sum())
        storage = _bytes_to_human(total_bytes)
    else:
        storage = "Pending"

    return {
        "datasets": datasets,
        "owners": owners,
        "departments": departments,
        "storage": storage,
    }


@router.get("/analytics/owners")
def owner_stats():
    df = load_datasets()

    if df.empty:
        return []

    result = df["owner"].value_counts().reset_index()
    result.columns = ["owner", "dataset_count"]

    return result.to_dict(orient="records")


@router.get("/analytics/departments")
def department_stats():
    df = load_datasets()

    if df.empty:
        return []

    result = df["lab/dept"].value_counts().reset_index()
    result.columns = ["lab/dept", "dataset_count"]

    return result.to_dict(orient="records")


@router.get("/analytics/recent-uploads")
def recent_uploads(limit: int = 5):
    """Return most recently created uploads (best-effort ordering)."""
    df = load_datasets()

    if df.empty:
        return []

    ts_col = _get_created_ts(df)
    if ts_col:
        df = df.sort_values(ts_col)

    # If no timestamp column exists, we keep the current order.
    recent = df.tail(limit)

    # Normalize payload for frontend.
    out = []
    for _, row in recent.iloc[::-1].iterrows():
        out.append(
            {
                "dataset_name": row.get("dataset_name") or row.get("name") or row.get("file_name") or "Untitled",
                "owner": row.get("owner") or "Unknown",
                "version": str(row.get("version") or row.get("dataset_version") or "v1"),
                "created_at": row.get(ts_col) if ts_col else None,
                "department": row.get("lab/dept") if "lab/dept" in df.columns else None,
            }
        )

    return out


@router.get("/analytics/active-users")
def active_users(window_days: int = 7, top_n: int = 5):
    """Best-effort: active users are inferred from recent uploads in the last window."""
    df = load_datasets()

    if df.empty:
        return {
            "active_users": 0,
            "top": [],
        }

    ts_col = _get_created_ts(df)
    if ts_col:
        # Best effort parsing; if parsing fails, fallback to tail-based inference.
        try:
            df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
            cutoff = pd.Timestamp.now(tz=None) - pd.Timedelta(days=window_days)
            window_df = df[df[ts_col] >= cutoff]
            if window_df.empty:
                window_df = df
        except Exception:
            window_df = df
    else:
        window_df = df.tail(30)

    if "owner" not in window_df.columns:
        return {"active_users": 0, "top": []}

    counts = (
        window_df["owner"]
        .value_counts()
        .head(top_n)
        .reset_index()
    )
    counts.columns = ["owner", "activity_count"]

    return {
        "active_users": int(window_df["owner"].nunique()),
        "top": counts.to_dict(orient="records"),
    }


@router.get("/analytics/storage-usage")
def storage_usage(quota_bytes: int = 50_000_000_000):
    """Return storage usage vs a quota.

    quota_bytes is a best-effort default. If your app has a real quota concept,
    we can replace this later.
    """
    df = load_datasets()

    used_bytes = 0
    if not df.empty and "size_bytes" in df.columns:
        used_bytes = float(df["size_bytes"].sum())

    quota_bytes = float(quota_bytes)
    used_pct = 0.0 if quota_bytes <= 0 else (used_bytes / quota_bytes) * 100.0

    # Breakdown by department (if available)
    breakdown = []
    if not df.empty and "size_bytes" in df.columns and "lab/dept" in df.columns:
        grouped = df.groupby("lab/dept")["size_bytes"].sum().sort_values(ascending=False).head(5)
        for dept, bytes_sum in grouped.items():
            breakdown.append(
                {
                    "label": str(dept),
                    "bytes": float(bytes_sum),
                    "percent": 0.0 if used_bytes <= 0 else (float(bytes_sum) / used_bytes) * 100.0,
                }
            )

    return {
        "used_bytes": used_bytes,
        "used": _bytes_to_human(used_bytes),
        "quota_bytes": quota_bytes,
        "quota": _bytes_to_human(quota_bytes),
        "used_pct": used_pct,
        "breakdown": breakdown,
    }
