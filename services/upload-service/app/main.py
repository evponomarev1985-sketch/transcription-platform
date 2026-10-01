from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jwt
import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .queue import publish_message
from .schemas import UploadAbortRequest, UploadCompleteRequest, UploadInitRequest, UploadInitResponse
from .security import parse_access_token
from .storage import create_presigned_put_url, delete_object, object_exists, upload_fileobj

settings = get_settings()
app = FastAPI(title="upload-service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".opus"}
SUPPORTED_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/opus",
    "application/ogg",
}


def _issue_upload_id(
    *,
    user_id: str,
    object_key: str,
    file_name: str,
    language: str,
    company_id: str | None,
    company_name: str | None,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "typ": "upload_init",
        "sub": user_id,
        "object_key": object_key,
        "file_name": file_name,
        "language": language,
        "company_id": company_id,
        "company_name": company_name,
        "iat": int(now.timestamp()),
        "exp": int((now.timestamp()) + 3600),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.upload_signing_secret, algorithm="HS256")


def _decode_upload_id(upload_id: str) -> dict:
    try:
        payload = jwt.decode(upload_id, settings.upload_signing_secret, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload_id") from exc
    if payload.get("typ") != "upload_init":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload_id type")
    return payload


def _validate_audio_support(file_name: str, mime_type: str) -> None:
    ext = Path(file_name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file extension")
    if mime_type.lower() not in SUPPORTED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported MIME type")


def _normalize_mime_type(file_name: str, mime_type: str | None) -> str:
    if mime_type:
        mime = mime_type.lower()
        if mime in SUPPORTED_MIME_TYPES:
            return mime
    ext = Path(file_name).suffix.lower()
    default_by_ext = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
    }
    return default_by_ext.get(ext, "application/octet-stream")


def _get_file_size(file_obj) -> int:
    current_pos = file_obj.tell()
    file_obj.seek(0, 2)
    size = file_obj.tell()
    file_obj.seek(current_pos)
    return size


@app.post("/api/v1/uploads/init", response_model=UploadInitResponse)
def init_upload(payload: UploadInitRequest, authorization: str | None = Header(default=None)) -> UploadInitResponse:
    user_payload = parse_access_token(authorization)
    if payload.file_size > settings.upload_max_file_size_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")
    _validate_audio_support(payload.file_name, payload.mime_type)

    object_key = f"uploads/{user_payload['sub']}/{uuid4()}-{payload.file_name}"
    upload_id = _issue_upload_id(
        user_id=str(user_payload["sub"]),
        object_key=object_key,
        file_name=payload.file_name,
        language=payload.language,
        company_id=str(user_payload.get("company_id") or "").strip() or None,
        company_name=str(user_payload.get("company_name") or "").strip() or None,
    )
    url = create_presigned_put_url(object_key, payload.mime_type)
    return UploadInitResponse(
        upload_id=upload_id,
        object_key=object_key,
        bucket=settings.yc_s3_bucket,
        presigned_url=url,
        expires_in_seconds=900,
    )


@app.post("/api/v1/uploads/direct")
def direct_upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    language: str = Form("ru-RU"),
    authorization: str | None = Header(default=None),
) -> dict:
    user_payload = parse_access_token(authorization)

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing file name")

    if _get_file_size(file.file) > settings.upload_max_file_size_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")

    detected_mime_type = _normalize_mime_type(file.filename, file.content_type)
    _validate_audio_support(file.filename, detected_mime_type)

    object_key = f"uploads/{user_payload['sub']}/{uuid4()}-{file.filename}"
    try:
        upload_fileobj(object_key, file.file, detected_mime_type)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to upload object") from exc
    finally:
        file.file.close()

    headers = {"x-internal-api-key": settings.call_service_internal_api_key}
    create_payload = {
        "owner_user_id": str(user_payload["sub"]),
        "owner_login": str(user_payload["login"]),
        "owner_company_id": str(user_payload.get("company_id") or "").strip() or None,
        "owner_company_name": str(user_payload.get("company_name") or "").strip() or None,
        "title": title,
        "source_file_name": file.filename,
        "object_key": object_key,
        "object_bucket": settings.yc_s3_bucket,
        "language": language,
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(f"{settings.call_service_internal_url}/internal/v1/calls", json=create_payload, headers=headers)
        if resp.status_code >= 300:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to create call")
        data = resp.json()

    message = {
        "schema_version": 1,
        "message_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "job_id": data["job_id"],
        "call_id": data["call_id"],
        "action": "SUBMIT",
        "attempt": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    publish_message(message)

    return {
        "call_id": data["call_id"],
        "job_id": data["job_id"],
        "status": "QUEUED",
    }


@app.post("/api/v1/uploads/{upload_id}/complete")
def complete_upload(
    upload_id: str,
    payload: UploadCompleteRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    user_payload = parse_access_token(authorization)
    upload_payload = _decode_upload_id(upload_id)

    if str(upload_payload["sub"]) != str(user_payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload does not belong to user")

    object_key = str(upload_payload["object_key"])
    if not object_exists(object_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Object not found in bucket")

    headers = {"x-internal-api-key": settings.call_service_internal_api_key}
    create_payload = {
        "owner_user_id": str(user_payload["sub"]),
        "owner_login": str(user_payload["login"]),
        "owner_company_id": str(user_payload.get("company_id") or upload_payload.get("company_id") or "").strip() or None,
        "owner_company_name": str(user_payload.get("company_name") or upload_payload.get("company_name") or "").strip() or None,
        "title": payload.title,
        "source_file_name": payload.file_name,
        "object_key": object_key,
        "object_bucket": settings.yc_s3_bucket,
        "language": payload.language,
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(f"{settings.call_service_internal_url}/internal/v1/calls", json=create_payload, headers=headers)
        if resp.status_code >= 300:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to create call")
        data = resp.json()

    message = {
        "schema_version": 1,
        "message_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "job_id": data["job_id"],
        "call_id": data["call_id"],
        "action": "SUBMIT",
        "attempt": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    publish_message(message)

    return {
        "upload_id": upload_id,
        "call_id": data["call_id"],
        "job_id": data["job_id"],
        "status": "QUEUED",
    }


@app.post("/api/v1/uploads/{upload_id}/abort")
def abort_upload(upload_id: str, payload: UploadAbortRequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    user_payload = parse_access_token(authorization)
    upload_payload = _decode_upload_id(upload_id)

    if str(upload_payload["sub"]) != str(user_payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload does not belong to user")

    object_key = str(upload_payload["object_key"])
    if object_exists(object_key):
        delete_object(object_key)

    return {"status": "aborted"}


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    return {"status": "ready"}
