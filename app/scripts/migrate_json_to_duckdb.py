"""
One-time migration: reads every storage/metadata/*.json file left over
from the old system and inserts it into DuckDB.

Run once from the backend/ directory:
    python -m app.scripts.migrate_json_to_duckdb

Safe to re-run — uses INSERT OR IGNORE on the image_id primary key,
so already-migrated rows are skipped rather than duplicated.
"""

import json
from pathlib import Path

from app.db import get_connection

METADATA_DIR = Path("storage/metadata")


def migrate():
    if not METADATA_DIR.exists():
        print(f"No {METADATA_DIR} directory found — nothing to migrate.")
        return

    conn = get_connection()
    migrated, skipped = 0, 0

    for file in METADATA_DIR.glob("*.json"):
        with open(file, "r") as f:
            data = json.load(f)

        # Some files may contain a single object {...}, others may
        # accidentally contain a list of objects [{...}, {...}].
        # Normalize to a list either way so both cases are handled.
        records = data if isinstance(data, list) else [data]

        for record in records:
            if not isinstance(record, dict):
                print(f"Skipping a record in {file.name} — not a JSON object")
                skipped += 1
                continue

            image_id = record.get("image_id")
            filename = record.get("filename")
            path = record.get("path", f"storage/uploads/{filename}")
            dataset_name = record.get("dataset_name")
            owner = record.get("owner")
            department = record.get("department") or record.get("lab/dept")
            version = record.get("version")

            known_keys = (
                "image_id", "filename", "path", "dataset_name",
                "owner", "department", "lab/dept", "version",
            )
            extra = {k: v for k, v in record.items() if k not in known_keys}

            if not image_id or not filename:
                print(f"Skipping a record in {file.name} — missing image_id/filename")
                skipped += 1
                continue

            existing = conn.execute(
                "SELECT 1 FROM datasets WHERE image_id = ?", [image_id]
            ).fetchone()

            if existing:
                skipped += 1
                continue

            conn.execute(
                """
                INSERT INTO datasets
                    (image_id, filename, path, dataset_name, owner, department, version, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [image_id, filename, path, dataset_name, owner, department, version, json.dumps(extra)],
            )
            migrated += 1

    print(f"Migration complete: {migrated} records migrated, {skipped} skipped.")


if __name__ == "__main__":
    migrate()