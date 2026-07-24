import os
from pathlib import Path
from typing import BinaryIO, Optional

from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Raw Dataset Bucket
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")

# Annotation / Project Bucket
AWS_S3_BUCKET_PROJECTS = os.getenv("AWS_S3_BUCKET_PROJECTS")

_s3_client = None


def get_s3_client():
    global _s3_client

    if _s3_client is None and (
        is_s3_enabled() or is_project_s3_enabled()
    ):
        _s3_client = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )

    return _s3_client


def is_s3_enabled() -> bool:
    """
    Returns True if the Raw Dataset bucket is configured.
    """
    return bool(
        AWS_ACCESS_KEY_ID
        and AWS_SECRET_ACCESS_KEY
        and AWS_S3_BUCKET
    )


def is_project_s3_enabled() -> bool:
    """
    Returns True if the Annotation / Project bucket is configured.
    """
    return bool(
        AWS_ACCESS_KEY_ID
        and AWS_SECRET_ACCESS_KEY
        and AWS_S3_BUCKET_PROJECTS
    )


def get_bucket_name() -> str:
    return AWS_S3_BUCKET or ""


def get_project_bucket_name() -> str:
    return AWS_S3_BUCKET_PROJECTS or ""


def upload_file_to_s3(
    file_path: Path,
    s3_key: str,
    bucket: Optional[str] = None,
) -> bool:
    """
    Upload a local file to S3.
    Used by the raw dataset upload workflow.
    """

    client = get_s3_client()

    if not client:
        return False

    bucket_name = bucket or AWS_S3_BUCKET

    try:
        print("=" * 60)
        print("S3 ENABLED")
        print("Bucket :", bucket_name)
        print("Region :", AWS_REGION)
        print("Key    :", s3_key)
        print("=" * 60)

        client.upload_file(
            str(file_path),
            bucket_name,
            s3_key,
        )

        return True

    except ClientError as e:
        print(f"S3 upload error: {e}")
        return False


def upload_fileobj_to_s3(
    file_obj: BinaryIO,
    s3_key: str,
    bucket: Optional[str] = None,
) -> bool:
    """
    Upload a file-like object directly to S3.
    """

    client = get_s3_client()

    if not client:
        return False

    bucket_name = bucket or AWS_S3_BUCKET

    try:
        client.upload_fileobj(
            file_obj,
            bucket_name,
            s3_key,
        )

        return True

    except ClientError as e:
        print(f"S3 upload_fileobj error: {e}")
        return False


def upload_bytes_to_s3(
    data: bytes,
    s3_key: str,
    bucket: Optional[str] = None,
    content_type: Optional[str] = None,
) -> bool:
    """
    Upload bytes directly to S3.

    Used by the annotation/project workflow so that
    images and JSON files never need to be written
    to local storage.
    """

    client = get_s3_client()

    if not client:
        return False

    bucket_name = bucket or AWS_S3_BUCKET

    try:
        kwargs = {}

        if content_type:
            kwargs["ContentType"] = content_type

        client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=data,
            **kwargs,
        )

        return True

    except ClientError as e:
        print(f"S3 upload bytes error: {e}")
        return False


def delete_file_from_s3(
    s3_key: str,
    bucket: Optional[str] = None,
) -> bool:
    """
    Delete an object from S3.
    """

    client = get_s3_client()

    if not client:
        return False

    bucket_name = bucket or AWS_S3_BUCKET

    try:
        client.delete_object(
            Bucket=bucket_name,
            Key=s3_key,
        )

        return True

    except ClientError as e:
        print(f"S3 delete error: {e}")
        return False


def get_s3_object_stream(
    s3_key: str,
    bucket: Optional[str] = None,
):
    """
    Return an S3 object's streaming body.
    """

    client = get_s3_client()

    if not client:
        return None

    bucket_name = bucket or AWS_S3_BUCKET

    try:
        response = client.get_object(
            Bucket=bucket_name,
            Key=s3_key,
        )

        return response["Body"]

    except ClientError as e:
        print(f"S3 get object stream error: {e}")
        return None


if __name__ == "__main__":

    test_file = Path("test.txt")

    success = upload_file_to_s3(
        test_file,
        "test/test.txt",
    )

    print("Upload Success:", success)