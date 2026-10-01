from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4
import re

import httpx
from fastapi import FastAPI

from .config import get_settings
from .queue import delete_message, publish_message, receive_messages
from .rules_client import get_enabled_llm_rules
from .speechkit import (
    extract_llm_rule_matches_from_v3,
    get_operation,
    normalize_segments_with_rules,
    submit_long_running_recognition,
)

settings = get_settings()
app = FastAPI(title="transcription-service", version="1.0.0")
log = logging.getLogger("transcription-service")
logging.basicConfig(level=logging.INFO)

_MONO_ONLY_LABELING_ERROR_RE = re.compile(r"speaker labeling is only for mono-channel audio files", re.IGNORECASE)

stop_event = threading.Event()
worker_thread: threading.Thread | None = None


def _headers() -> dict[str, str]:
    return {"x-internal-api-key": settings.internal_api_key}


def _call_service_get_job(job_id: str) -> dict:
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{settings.call_service_internal_url}/internal/v1/jobs/{job_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _call_service_get_call(call_id: str) -> dict:
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{settings.call_service_internal_url}/internal/v1/calls/{call_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _call_service_post(path: str, payload: dict | None = None) -> dict:
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(f"{settings.call_service_internal_url}{path}", headers=_headers(), json=payload or {})
        resp.raise_for_status()
        return resp.json()


def _publish_check_result(call_id: str, job_id: str, attempt: int) -> None:
    publish_message(
        {
            "schema_version": 1,
            "message_id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "job_id": job_id,
            "call_id": call_id,
            "action": "CHECK_RESULT",
            "attempt": attempt,
            "created_at": datetime.now(UTC).isoformat(),
        },
        delay_seconds=settings.speechkit_poll_delay_seconds,
    )


def _handle_submit(message: dict) -> None:
    job_id = str(message["job_id"])
    call_id = str(message["call_id"])
    job = _call_service_get_job(job_id)

    if job["status"] in {"COMPLETED", "FAILED"}:
        return

    if job.get("operation_id"):
        _publish_check_result(call_id, job_id, int(message.get("attempt", 0)) + 1)
        return

    _call_service_post(f"/internal/v1/jobs/{job_id}/mark-processing")
    call = _call_service_get_call(call_id)
    audio_uri = f"https://storage.yandexcloud.net/{call['object_bucket']}/{call['object_key']}"
    llm_rules = get_enabled_llm_rules() if settings.speechkit_api_version.lower() == "v3" else []
    llm_rules = [rule for rule in llm_rules if str(rule.get("prompt", "")).strip()]

    try:
        operation_id = submit_long_running_recognition(
            audio_uri,
            call.get("language", settings.speechkit_language),
            source_file_name=call.get("source_file_name"),
            llm_rules=llm_rules,
        )
    except Exception as exc:
        if _MONO_ONLY_LABELING_ERROR_RE.search(str(exc)):
            operation_id = submit_long_running_recognition(
                audio_uri,
                call.get("language", settings.speechkit_language),
                source_file_name=call.get("source_file_name"),
                speaker_labeling_enabled=False,
                llm_rules=llm_rules,
            )
        else:
            raise
    _call_service_post(f"/internal/v1/jobs/{job_id}/register-operation", {"operation_id": operation_id})
    _publish_check_result(call_id, job_id, int(message.get("attempt", 0)) + 1)


def _handle_check_result(message: dict) -> None:
    job_id = str(message["job_id"])
    job = _call_service_get_job(job_id)

    if job["status"] in {"COMPLETED", "FAILED"}:
        return

    operation_id = job.get("operation_id")
    if not operation_id:
        _call_service_post(f"/internal/v1/jobs/{job_id}/fail", {"error_message": "operation_id is missing"})
        return

    op = get_operation(str(operation_id))
    if not op.get("done", False):
        attempt = int(message.get("attempt", 0)) + 1
        if attempt > settings.speechkit_max_attempts:
            _call_service_post(f"/internal/v1/jobs/{job_id}/fail", {"error_message": "SpeechKit operation timeout"})
            return
        _publish_check_result(str(message["call_id"]), job_id, attempt)
        return

    if op.get("error"):
        err = op["error"].get("message", "SpeechKit operation failed")
        _call_service_post(f"/internal/v1/jobs/{job_id}/fail", {"error_message": err})
        return

    llm_rules = get_enabled_llm_rules() if settings.speechkit_api_version.lower() == "v3" else []
    normalized = normalize_segments_with_rules(op, llm_rules=llm_rules, operation_id=str(operation_id))
    call = _call_service_get_call(str(message["call_id"]))
    llm_matches = normalized.get("llm_rule_matches", [])
    if settings.speechkit_api_version.lower() == "v3" and not llm_matches and llm_rules:
        llm_matches = extract_llm_rule_matches_from_v3(str(operation_id))

    _call_service_post(
        f"/internal/v1/jobs/{job_id}/complete",
        {
            "full_text": normalized["full_text"],
            "language": call.get("language", settings.speechkit_language),
            "segments": normalized["segments"],
            "llm_rule_matches": llm_matches,
        },
    )


def _process_message(raw_message: dict) -> None:
    body = raw_message.get("Body", "{}")
    message = json.loads(body)
    action = message.get("action")
    if action == "SUBMIT":
        _handle_submit(message)
    elif action == "CHECK_RESULT":
        _handle_check_result(message)
    else:
        log.warning("Unknown action=%s message_id=%s", action, message.get("message_id"))


def worker_loop() -> None:
    while not stop_event.is_set():
        try:
            messages = receive_messages(max_number=5, wait_seconds=20)
            if not messages:
                continue

            for msg in messages:
                receipt = msg.get("ReceiptHandle")
                try:
                    _process_message(msg)
                    if receipt:
                        delete_message(receipt)
                except Exception as exc:
                    log.exception("Message processing failed: %s", exc)
        except Exception as exc:
            log.exception("Worker loop error: %s", exc)
            time.sleep(3)


@app.on_event("startup")
def startup() -> None:
    global worker_thread
    stop_event.clear()
    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    stop_event.set()
    if worker_thread and worker_thread.is_alive():
        worker_thread.join(timeout=10)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    return {"status": "ready"}
