from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import threading

import httpx

from .config import get_settings


@dataclass(slots=True)
class CachedToken:
    token: str
    expires_at: datetime


_lock = threading.Lock()
_cached: CachedToken | None = None


def _parse_expiry(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC) + timedelta(hours=1)
    raw = value.replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


def _fetch_iam_token_from_metadata() -> CachedToken:
    s = get_settings()
    headers = {"Metadata-Flavor": "Google"}
    with httpx.Client(timeout=s.yc_metadata_timeout_seconds) as client:
        resp = client.get(s.yc_metadata_token_url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    token = data.get("access_token")
    if not token:
        raise ValueError("Metadata token response does not contain access_token")
    expires_at = _parse_expiry(data.get("expires_at"))
    return CachedToken(token=str(token), expires_at=expires_at)


def get_iam_token() -> str:
    global _cached

    s = get_settings()
    if s.yc_iam_token_source.lower() == "env":
        if not s.yc_iam_token:
            raise ValueError("YC_IAM_TOKEN is required when YC_IAM_TOKEN_SOURCE=env")
        return s.yc_iam_token

    now = datetime.now(UTC)
    margin = timedelta(seconds=s.yc_metadata_refresh_margin_seconds)

    with _lock:
        if _cached and (_cached.expires_at - margin) > now:
            return _cached.token

        _cached = _fetch_iam_token_from_metadata()
        return _cached.token
