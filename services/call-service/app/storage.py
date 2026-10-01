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


def create_presigned_get_url(object_key: str, expires_seconds: int = 3600) -> str:
    s = get_settings()
    client = build_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": s.yc_s3_bucket, "Key": object_key},
        ExpiresIn=expires_seconds,
    )


def get_object(object_key: str, byte_range: str | None = None) -> dict:
    s = get_settings()
    client = build_s3_client()
    params = {"Bucket": s.yc_s3_bucket, "Key": object_key}
    if byte_range:
        params["Range"] = byte_range
    return client.get_object(**params)
