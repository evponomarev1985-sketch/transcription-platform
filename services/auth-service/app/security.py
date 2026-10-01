from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import get_settings

ph = PasswordHasher()


@dataclass(slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    refresh_token_hash: str
    refresh_expires_at: datetime


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def create_token_pair(
    user_id: str,
    login: str,
    role: str,
    *,
    company_id: str | None = None,
    company_name: str | None = None,
) -> TokenPair:
    settings = get_settings()
    now = datetime.now(UTC)

    access_payload: dict[str, Any] = {
        "sub": user_id,
        "login": login,
        "role": role,
        "company_id": company_id,
        "company_name": company_name,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_ttl_minutes)).timestamp()),
        "jti": str(uuid4()),
    }
    access = jwt.encode(access_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    refresh_plain = secrets.token_urlsafe(64)
    refresh_exp = now + timedelta(days=settings.jwt_refresh_ttl_days)
    refresh_payload: dict[str, Any] = {
        "sub": user_id,
        "login": login,
        "role": role,
        "company_id": company_id,
        "company_name": company_name,
        "typ": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(refresh_exp.timestamp()),
        "jti": str(uuid4()),
        "rti": refresh_plain,
    }
    refresh = jwt.encode(refresh_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        refresh_token_hash=hash_refresh_token(refresh),
        refresh_expires_at=refresh_exp,
    )


def decode_refresh_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != "refresh":
        raise ValueError("Invalid token type")
    return payload
