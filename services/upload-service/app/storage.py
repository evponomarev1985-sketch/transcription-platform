from __future__ import annotations

import boto3

from .config import get_settings


def build_s3_client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.yc_s3_endpoint,
        region_name=s.yc_s3_region,
        aws_access_key_id=s.yc_access_key_id,
        aws_secret_access_key=s.yc_secret_access_key,
    )


def create_presigned_put_url(object_key: str, mime_type: str, expires_seconds: int = 900) -> str:
    s = get_settings()
    client = build_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": s.yc_s3_bucket, "Key": object_key, "ContentType": mime_type},
        ExpiresIn=expires_seconds,
    )


def object_exists(object_key: str) -> bool:
    s = get_settings()
    client = build_s3_client()
    try:
        client.head_object(Bucket=s.yc_s3_bucket, Key=object_key)
        return True
    except Exception:
        return False


def delete_object(object_key: str) -> None:
    s = get_settings()
    client = build_s3_client()
    client.delete_object(Bucket=s.yc_s3_bucket, Key=object_key)


def upload_fileobj(object_key: str, fileobj, mime_type: str) -> None:
    s = get_settings()
    client = build_s3_client()
    client.upload_fileobj(
        fileobj,
        s.yc_s3_bucket,
        object_key,
        ExtraArgs={"ContentType": mime_type},
    )
