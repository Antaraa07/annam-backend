from fastapi import APIRouter, HTTPException
from pathlib import Path
import json

router = APIRouter()

METADATA_DIR = Path("storage/metadata")


@router.get("/datasets")
def list_datasets():

    datasets = []

    for file in METADATA_DIR.glob("*.json"):

        if file.name == "projects.json":
            continue

        with open(file, "r") as f:
            data = json.load(f)

        datasets.append(data)

    return datasets


@router.get("/dataset/{image_id}")
def get_dataset(image_id: str):

    metadata_file = METADATA_DIR / f"{image_id}.json"

    if not metadata_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    with open(metadata_file, "r") as f:
        data = json.load(f)

    return data