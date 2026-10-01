from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin
from ..models import User, UserRole
from ..schemas import AdminCreateUserRequest, AdminUpdateUserRequest, UserListOut, UserOut
from ..security import hash_password

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        login=user.login,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
        is_blocked=user.is_blocked,
        created_at=user.created_at,
    )


@router.get("/users", response_model=UserListOut)
def list_users(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListOut:
    total = db.scalar(select(func.count(User.id))) or 0
    users = db.scalars(select(User).order_by(User.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    return UserListOut(items=[_user_out(u) for u in users], page=page, size=size, total=int(total))


@router.post("/users", response_model=UserOut)
def create_user(payload: AdminCreateUserRequest, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> UserOut:
    existing = db.execute(select(User).where(func.lower(User.login) == payload.login.lower())).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Login already exists")
    user = User(
        login=payload.login,
        email=str(payload.email) if payload.email else None,
        password_hash=hash_password(payload.password),
        role=UserRole(payload.role),
        is_active=payload.is_active,
        is_blocked=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, payload: AdminUpdateUserRequest, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> UserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.email is not None:
        user.email = str(payload.email)
    if payload.role is not None:
        user.role = UserRole(payload.role)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_blocked is not None:
        user.is_blocked = payload.is_blocked
    if payload.password:
        user.password_hash = hash_password(payload.password)

    db.commit()
    db.refresh(user)
    return _user_out(user)
