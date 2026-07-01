from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter()

METADATA_DIR = Path("storage/metadata")


@router.get("/search")
def search_datasets(dataset_name: str):

    results = []

    for file in METADATA_DIR.glob("*.json"):

        with open(file, "r") as f:
            data = json.load(f)

        if dataset_name.lower() in data.get(
            "dataset_name", ""
        ).lower():

            results.append(data)

    return results