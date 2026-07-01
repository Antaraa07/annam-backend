from fastapi import APIRouter
from app.services.analytics_service import load_datasets
import duckdb

router = APIRouter()


@router.get("/analytics/departments")
def department_stats():

    df = load_datasets()

    if df.empty:
        return []

    conn = duckdb.connect()

    conn.register(
        "datasets",
        df
    )

    result = conn.execute("""
        SELECT
            "lab/dept",
            COUNT(*) AS dataset_count
        FROM datasets
        GROUP BY "lab/dept"
    """).fetchdf()

    conn.close()

    return result.to_dict(
        orient="records"
    )