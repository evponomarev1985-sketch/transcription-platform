from __future__ import annotations

from typing import Any

import jwt
from fastapi import Header, HTTPException, status
from jwt import InvalidTokenError

from .config import get_settings


def parse_access_token(authorization: str | None) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")

    settings = get_settings()
    try:
        payload = jwt.decode(
            parts[1],
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "role", "login", "typ"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if payload.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


def require_internal_api_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_internal_api_key != settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API key")
