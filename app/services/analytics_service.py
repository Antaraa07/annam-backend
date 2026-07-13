from app.db import run_df, run_one, run_raw


def load_datasets():
    """
    Drop-in replacement for the old JSON-scanning version.
    Same return shape (a DataFrame of all datasets), but backed by
    a single indexed SQL query instead of opening every file on disk.
    """
    return run_df("SELECT * FROM datasets ORDER BY uploaded_at DESC")


def get_summary(username: str | None = None):
    """Powers /analytics/summary"""
    where = "WHERE owner = ?" if username else ""
    params = [username] if username else []
    row = run_one(
        f"""
        SELECT
            count(*)                          AS total_datasets,
            count(DISTINCT owner)             AS total_owners,
            count(DISTINCT department)        AS total_departments,
            max(uploaded_at)                  AS last_upload_at
        FROM datasets
        {where}
        """,
        params,
    )

    return {
        "datasets": row[0],
        "owners": row[1],
        "departments": row[2],
        # No file-size column exists in the schema yet.
        "storage": "Pending",
        "last_upload_at": row[3].isoformat() if row[3] else None,
    }


def get_by_owner():
    """Powers /analytics/owners"""
    rows = run_raw(
        """
        SELECT owner, count(*) AS dataset_count
        FROM datasets
        WHERE owner IS NOT NULL
        GROUP BY owner
        ORDER BY dataset_count DESC
        """
    )
    return [{"owner": r[0], "dataset_count": r[1]} for r in rows]


def get_by_department(username: str | None = None):
    """Powers /analytics/departments"""
    where = "AND owner = ?" if username else ""
    params = [username] if username else []
    rows = run_raw(
        f"""
        SELECT department, count(*) AS dataset_count
        FROM datasets
        WHERE department IS NOT NULL {where}
        GROUP BY department
        ORDER BY dataset_count DESC
        """,
        params,
    )
    return [{"department": r[0], "dataset_count": r[1]} for r in rows]


def get_recent(limit: int = 10, username: str | None = None):
    """Powers /analytics/recent and /analytics/recent-uploads"""
    where = "AND owner = ?" if username else ""
    params = [username, limit] if username else [limit]
    rows = run_raw(
        f"""
        SELECT image_id, filename, dataset_name, owner, department, version, uploaded_at
        FROM datasets
        WHERE 1=1 {where}
        ORDER BY uploaded_at DESC
        LIMIT ?
        """,
        params,
    )
    return [
        {
            "image_id": r[0],
            "filename": r[1],
            "dataset_name": r[2] or r[1] or "Untitled",
            "owner": r[3] or "Unknown",
            "department": r[4] or "Unassigned",
            "version": r[5] or "v1",
            "uploaded_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


def get_active_users(limit: int = 10):
    """Powers /analytics/active-users — owners ranked by upload count."""
    rows = run_raw(
        """
        SELECT owner, count(*) AS upload_count, max(uploaded_at) AS last_upload_at
        FROM datasets
        WHERE owner IS NOT NULL
        GROUP BY owner
        ORDER BY upload_count DESC
        LIMIT ?
        """,
        [limit],
    )
    return [
        {
            "owner": r[0],
            "upload_count": r[1],
            "last_upload_at": r[2].isoformat() if r[2] else None,
        }
        for r in rows
    ]