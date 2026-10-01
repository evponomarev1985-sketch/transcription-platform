from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from jwt import InvalidTokenError


class JWTAuthError(Exception):
    pass


@dataclass(slots=True)
class JWTUser:
    sub: str
    login: str
    role: str


def decode_access_token(token: str, secret: str, algorithm: str = "HS256") -> JWTUser:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["sub", "exp", "iat", "role", "login", "typ"]},
        )
    except InvalidTokenError as exc:
        raise JWTAuthError("Invalid access token") from exc

    if payload.get("typ") != "access":
        raise JWTAuthError("Invalid token type")

    return JWTUser(
        sub=str(payload["sub"]),
        login=str(payload["login"]),
        role=str(payload["role"]),
    )
