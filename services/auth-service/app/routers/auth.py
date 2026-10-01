from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user
from ..models import Company, RefreshSession, User, UserRole
from ..schemas import (
    AuthTokensOut,
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RegisterRequest,
    RefreshRequest,
    UpdateProfileRequest,
    UserOut,
)
from ..security import create_token_pair, decode_refresh_token, hash_password, hash_refresh_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        login=user.login,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        company_id=user.company_id,
        company_name=user.company.name if user.company else None,
        role=user.role.value,
        is_active=user.is_active,
        is_blocked=user.is_blocked,
        marketing_consent=user.marketing_consent,
        created_at=user.created_at,
    )


def _normalized_company_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _get_or_create_company(db: Session, company_name: str) -> Company:
    normalized_name = _normalized_company_name(company_name)
    company = db.execute(select(Company).where(Company.normalized_name == normalized_name)).scalar_one_or_none()
    if company:
        return company

    company = Company(name=company_name.strip(), normalized_name=normalized_name, is_active=True)
    db.add(company)
    db.flush()
    return company


def _tokens_out(user: User, access_token: str, refresh_token: str) -> AuthTokensOut:
    settings = get_settings()
    return AuthTokensOut(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=settings.jwt_access_ttl_minutes * 60,
        user=_user_out(user),
    )


@router.post("/login", response_model=AuthTokensOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> AuthTokensOut:
    stmt = select(User).where(
        or_(func.lower(User.login) == payload.login_or_email.lower(), func.lower(User.email) == payload.login_or_email.lower())
    )
    user = db.execute(stmt).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active or user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive or blocked")

    pair = create_token_pair(
        user.id,
        user.login,
        user.role.value,
        company_id=user.company_id,
        company_name=user.company.name if user.company else None,
    )
    session = RefreshSession(
        user_id=user.id,
        token_hash=pair.refresh_token_hash,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        expires_at=pair.refresh_expires_at,
    )
    db.add(session)
    db.commit()
    return _tokens_out(user, pair.access_token, pair.refresh_token)


@router.post("/refresh", response_model=AuthTokensOut)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> AuthTokensOut:
    try:
        data = decode_refresh_token(payload.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    token_hash = hash_refresh_token(payload.refresh_token)
    session = db.execute(select(RefreshSession).where(RefreshSession.token_hash == token_hash)).scalar_one_or_none()
    if not session or session.revoked_at is not None or session.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session is invalid")

    user = db.get(User, str(data["sub"]))
    if not user or not user.is_active or user.is_blocked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or blocked")

    session.revoked_at = datetime.now(UTC)
    pair = create_token_pair(
        user.id,
        user.login,
        user.role.value,
        company_id=user.company_id,
        company_name=user.company.name if user.company else None,
    )
    new_session = RefreshSession(
        user_id=user.id,
        token_hash=pair.refresh_token_hash,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        expires_at=pair.refresh_expires_at,
    )
    db.add(new_session)
    db.commit()
    return _tokens_out(user, pair.access_token, pair.refresh_token)


@router.post("/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    token_hash = hash_refresh_token(payload.refresh_token)
    session = db.execute(select(RefreshSession).where(RefreshSession.token_hash == token_hash)).scalar_one_or_none()
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.commit()
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


@router.patch("/password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wrong old password")
    user.password_hash = hash_password(payload.new_password)
    db.execute(
        select(RefreshSession).where(RefreshSession.user_id == user.id)
    )
    for item in db.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id)):
        item.revoked_at = datetime.now(UTC)
    db.commit()
    return {"status": "ok"}


@router.post("/register", response_model=UserOut)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserOut:
    settings = get_settings()
    if not settings.auth_registration_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration disabled")
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    if not payload.terms_accepted or not payload.privacy_accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Terms and privacy consent are required")

    email = str(payload.work_email).strip().lower()
    existing_login = db.execute(select(User).where(func.lower(User.login) == email)).scalar_one_or_none()
    existing_email = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    if existing_login or existing_email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    company = _get_or_create_company(db, payload.company_name)
    now = datetime.now(UTC)
    user = User(
        login=email,
        email=email,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        company_id=company.id,
        password_hash=hash_password(payload.password),
        role=UserRole.USER,
        marketing_consent=payload.marketing_consent,
        terms_accepted_at=now,
        privacy_accepted_at=now,
        is_active=True,
        is_blocked=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    email = str(payload.work_email).strip().lower()
    existing_email_user = db.execute(
        select(User).where(func.lower(User.email) == email, User.id != user.id)
    ).scalar_one_or_none()
    if existing_email_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    company = _get_or_create_company(db, payload.company_name)
    user.first_name = payload.first_name.strip()
    user.last_name = payload.last_name.strip()
    user.email = email
    user.company_id = company.id
    user.marketing_consent = payload.marketing_consent

    db.commit()
    db.refresh(user)
    return _user_out(user)
