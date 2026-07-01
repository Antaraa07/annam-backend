from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter()

METADATA_DIR = Path("storage/metadata")


@router.get("/versions/{dataset_name}")
def get_versions(dataset_name: str):

    versions = []

    for file in METADATA_DIR.glob("*.json"):

        with open(file, "r") as f:
            data = json.load(f)

        if data.get(
            "dataset_name", ""
        ).lower() == dataset_name.lower():

            versions.append({
                "image_id": data["image_id"],
                "version": data["version"],
                "owner": data["owner"]
            })

    return versions