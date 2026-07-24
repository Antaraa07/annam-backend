import json
from pathlib import PurePosixPath

from fastapi import HTTPException

from app.services.s3_service import (
    upload_bytes_to_s3,
    get_project_bucket_name,
)


def save_annotation_file(
    image_file,
    annotation_json: dict | None,
    metadata: dict,
):
    """
    Upload an annotated image and its LabelMe JSON directly to the
    project S3 bucket.

    Structure created in S3:

    dataset/
        version/
            images/
            annotations/

    No local files are created.
    No DuckDB entries.
    No DynamoDB entries.
    """

    bucket = get_project_bucket_name()

    if not bucket:
        raise HTTPException(
            status_code=500,
            detail="Project bucket not configured."
        )

    dataset_name = (
        metadata.get("dataset_name", "dataset")
        .strip()
        .replace(" ", "_")
    )

    version = (
        metadata.get("version", "v1")
        .strip()
        .replace(" ", "_")
    )

    original_filename = PurePosixPath(image_file.filename).name
    image_stem = PurePosixPath(original_filename).stem
    image_extension = PurePosixPath(original_filename).suffix

    image_key = (
        f"{dataset_name}/"
        f"{version}/"
        f"images/"
        f"{image_stem}{image_extension}"
    )

    json_key = (
        f"{dataset_name}/"
        f"{version}/"
        f"annotations/"
        f"{image_stem}.json"
    )

    image_bytes = image_file.file.read()
    print("\n" + "=" * 60)
    print("ANNOTATION SERVICE CALLED")
    print("Original File :", original_filename)
    print("Bucket        :", bucket)
    print("Image Key     :", image_key)
    print("JSON Key      :", json_key)
    print("=" * 60 + "\n")


    success = upload_bytes_to_s3(
        data=image_bytes,
        s3_key=image_key,
        bucket=bucket,
        content_type=image_file.content_type,
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to upload image."
        )

    if annotation_json is not None:

        json_bytes = json.dumps(
            annotation_json,
            indent=2,
        ).encode("utf-8")

        success = upload_bytes_to_s3(
            data=json_bytes,
            s3_key=json_key,
            bucket=bucket,
            content_type="application/json",
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload annotation JSON."
            )

    return {
        "filename": original_filename,
        "image_key": image_key,
        "json_key": json_key if annotation_json is not None else None,
    }