from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    login_or_email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    login_or_email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    login: str
    email: str | None
    role: Literal["USER", "ADMIN"]
    is_active: bool
    is_blocked: bool
    created_at: datetime


class AuthTokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    user: UserOut


class AdminCreateUserRequest(BaseModel):
    login: str = Field(min_length=3, max_length=128)
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=128)
    role: Literal["USER", "ADMIN"] = "USER"
    is_active: bool = True


class AdminUpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    role: Literal["USER", "ADMIN"] | None = None
    is_active: bool | None = None
    is_blocked: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserListOut(BaseModel):
    items: list[UserOut]
    page: int
    size: int
    total: int
