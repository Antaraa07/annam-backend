"""
Central DuckDB connection manager.

Import `get_connection()` anywhere you need to talk to the database.
DuckDB is embedded (like SQLite) — one file on disk, no server process.
"""

import duckdb
import threading
from pathlib import Path

DB_PATH = Path("storage/annam.duckdb")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_connection = None


def get_connection():
    """
    Returns a singleton DuckDB connection.
    Only sets up the connection — does NOT protect query execution.
    Use `run(...)`, `run_df(...)`, etc. below for actual queries; those
    hold `_lock` for the full duration of the call. FastAPI runs sync
    routes in a thread pool, so several requests (e.g. your dashboard's
    parallel Promise.all polling) can genuinely call into DuckDB at the
    same time, and DuckDB's Python connection object is not safe for
    concurrent use from multiple threads — hence the lock.
    """
    global _connection
    if _connection is None:
        with _lock:
            if _connection is None:
                _connection = duckdb.connect(str(DB_PATH))
                _init_schema(_connection)
    return _connection


def _init_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            image_id      VARCHAR PRIMARY KEY,
            filename      VARCHAR NOT NULL,
            path          VARCHAR NOT NULL,
            dataset_name  VARCHAR,
            owner         VARCHAR,
            department    VARCHAR,
            version       VARCHAR,
            project_id    VARCHAR,
            label         VARCHAR,
            uploaded_at   TIMESTAMP DEFAULT current_timestamp,
            metadata_json JSON
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_updates (
            update_id   VARCHAR PRIMARY KEY,
            username    VARCHAR NOT NULL,
            work_date   DATE NOT NULL,
            project     VARCHAR,
            work_done   VARCHAR NOT NULL,
            status      VARCHAR NOT NULL DEFAULT 'in_progress',
            next_steps  VARCHAR,
            created_at  TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    # Safe to re-run: adds columns if migrating an older DB that predates them.
    for col_def in [
        "dataset_name VARCHAR",
        "version VARCHAR",
        "project_id VARCHAR",
        "label VARCHAR",
    ]:
        try:
            conn.execute(f"ALTER TABLE datasets ADD COLUMN {col_def}")
        except duckdb.CatalogException:
            pass  # column already exists

    # Helpful for the analytics group-by queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_datasets_owner ON datasets(owner)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_datasets_department ON datasets(department)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_datasets_project_id ON datasets(project_id)")


def run(query: str, params: list | None = None):
    """
    Run a read query and return results as a list of dicts.
    Uses a fresh cursor per call (no lock) — DuckDB supports concurrent
    reads safely; only writes need to be serialized.
    """
    conn = get_connection()
    cursor = conn.cursor()
    result = cursor.execute(query, params or [])
    columns = [c[0] for c in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def run_raw(query: str, params: list | None = None):
    """Read-only, no lock. Returns raw tuples via fetchall()."""
    conn = get_connection()
    cursor = conn.cursor()
    return cursor.execute(query, params or []).fetchall()


def run_one(query: str, params: list | None = None):
    """Read-only, no lock. Returns a single row via fetchone()."""
    conn = get_connection()
    cursor = conn.cursor()
    return cursor.execute(query, params or []).fetchone()


def run_df(query: str):
    """Read-only, no lock. Returns a DataFrame via .df()."""
    conn = get_connection()
    cursor = conn.cursor()
    return cursor.execute(query).df()


def run_execute(query: str, params: list | None = None):
    """
    Write query (INSERT/DELETE/UPDATE). Holds the lock for the full
    duration — writes must be serialized to avoid corrupting the
    shared connection state.
    """
    with _lock:
        conn = get_connection()
        conn.execute(query, params or [])


# Kept for backwards compatibility with earlier code.
execute_query = run
