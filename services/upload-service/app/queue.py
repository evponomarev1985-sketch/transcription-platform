from __future__ import annotations

import json

import boto3

from .config import get_settings


def build_queue_client():
    s = get_settings()
    return boto3.client(
        "sqs",
        endpoint_url=s.ymq_endpoint_url,
        region_name=s.ymq_region,
        aws_access_key_id=s.ymq_access_key_id,
        aws_secret_access_key=s.ymq_secret_access_key,
    )


def publish_message(payload: dict) -> None:
    s = get_settings()
    client = build_queue_client()
    client.send_message(QueueUrl=s.ymq_queue_url, MessageBody=json.dumps(payload, ensure_ascii=True))
