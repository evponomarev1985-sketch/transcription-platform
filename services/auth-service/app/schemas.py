from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    login_or_email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    work_email: EmailStr
    company_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)
    terms_accepted: bool
    privacy_accepted: bool
    marketing_consent: bool = False


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
    first_name: str | None
    last_name: str | None
    company_id: str | None
    company_name: str | None
    role: Literal["USER", "ADMIN"]
    is_active: bool
    is_blocked: bool
    marketing_consent: bool
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    work_email: EmailStr
    company_name: str = Field(min_length=1, max_length=255)
    marketing_consent: bool = False


class AuthTokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    user: UserOut


class AdminCreateUserRequest(BaseModel):
    login: str = Field(min_length=3, max_length=128)
    email: EmailStr | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=128)
    last_name: str | None = Field(default=None, min_length=1, max_length=128)
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["USER", "ADMIN"] = "USER"
    is_active: bool = True
    marketing_consent: bool = False


class AdminUpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=128)
    last_name: str | None = Field(default=None, min_length=1, max_length=128)
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Literal["USER", "ADMIN"] | None = None
    is_active: bool | None = None
    is_blocked: bool | None = None
    marketing_consent: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserListOut(BaseModel):
    items: list[UserOut]
    page: int
    size: int
    total: int
