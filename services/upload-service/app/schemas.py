from __future__ import annotations

from pydantic import BaseModel, Field


class UploadInitRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0)
    mime_type: str = Field(min_length=1, max_length=255)
    language: str = "ru-RU"


class UploadInitResponse(BaseModel):
    upload_id: str
    object_key: str
    bucket: str
    presigned_url: str
    expires_in_seconds: int


class UploadCompleteRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    language: str = "ru-RU"
    title: str = Field(min_length=1, max_length=255)


class UploadAbortRequest(BaseModel):
    reason: str | None = None
