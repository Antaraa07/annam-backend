import uuid
import shutil
import json
from pathlib import Path


UPLOAD_DIR = Path("storage/uploads")
METADATA_DIR = Path("storage/metadata")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR.mkdir(parents=True, exist_ok=True)


def save_file(file, metadata):

    image_id = str(uuid.uuid4())

    extension = file.filename.split(".")[-1]

    filename = f"{image_id}.{extension}"

    file_path = UPLOAD_DIR / filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    metadata_path = METADATA_DIR / f"{image_id}.json"

    with open(metadata_path, "w") as meta_file:
        json.dump(
            {
                "image_id": image_id,
                "filename": filename,
                **metadata
            },
            meta_file,
            indent=4
        )

    return {
        "image_id": image_id,
        "filename": filename,
        "path": str(file_path)
    }