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


def receive_messages(max_number: int = 5, wait_seconds: int = 20) -> list[dict]:
    s = get_settings()
    client = build_queue_client()
    response = client.receive_message(
        QueueUrl=s.ymq_queue_url,
        MaxNumberOfMessages=max_number,
        WaitTimeSeconds=wait_seconds,
        VisibilityTimeout=120,
    )
    return response.get("Messages", [])


def delete_message(receipt_handle: str) -> None:
    s = get_settings()
    client = build_queue_client()
    client.delete_message(QueueUrl=s.ymq_queue_url, ReceiptHandle=receipt_handle)


def publish_message(payload: dict, delay_seconds: int = 0) -> None:
    s = get_settings()
    client = build_queue_client()
    client.send_message(
        QueueUrl=s.ymq_queue_url,
        MessageBody=json.dumps(payload, ensure_ascii=True),
        DelaySeconds=delay_seconds,
    )
