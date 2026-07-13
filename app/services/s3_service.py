import os
from pathlib import Path
from typing import BinaryIO
import boto3
from botocore.exceptions import ClientError

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None and is_s3_enabled():
        _s3_client = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )
    return _s3_client


def is_s3_enabled() -> bool:
    return bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_S3_BUCKET)


def get_bucket_name() -> str:
    return AWS_S3_BUCKET or ""


def upload_file_to_s3(file_path: Path, s3_key: str) -> bool:
    client = get_s3_client()
    if not client:
        return False
    try:
        client.upload_file(str(file_path), AWS_S3_BUCKET, s3_key)
        return True
    except ClientError as e:
        print(f"S3 upload error: {e}")
        return False


def upload_fileobj_to_s3(file_obj: BinaryIO, s3_key: str) -> bool:
    client = get_s3_client()
    if not client:
        return False
    try:
        client.upload_fileobj(file_obj, AWS_S3_BUCKET, s3_key)
        return True
    except ClientError as e:
        print(f"S3 upload_fileobj error: {e}")
        return False


def delete_file_from_s3(s3_key: str) -> bool:
    client = get_s3_client()
    if not client:
        return False
    try:
        client.delete_object(Bucket=AWS_S3_BUCKET, Key=s3_key)
        return True
    except ClientError as e:
        print(f"S3 delete error: {e}")
        return False


def get_s3_object_stream(s3_key: str):
    client = get_s3_client()
    if not client:
        return None
    try:
        response = client.get_object(Bucket=AWS_S3_BUCKET, Key=s3_key)
        return response["Body"]
    except ClientError as e:
        print(f"S3 get object stream error: {e}")
        return None
