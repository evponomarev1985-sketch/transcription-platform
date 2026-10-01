from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LabelDefinition, LabelKind
from ..schemas import LabelDefinitionCreateRequest, LabelDefinitionListOut, LabelDefinitionOut
from ..security import parse_access_token

router = APIRouter(prefix="/api/v1/calls/labels", tags=["label-definitions"])


def _ensure_admin(authorization: str | None) -> None:
    payload = parse_access_token(authorization)
    if str(payload.get("role")) != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _out(ld: LabelDefinition) -> LabelDefinitionOut:
    return LabelDefinitionOut(
        id=ld.id,
        code=ld.code,
        name=ld.name,
        kind=ld.kind.value,
        is_active=ld.is_active,
        created_at=ld.created_at,
        updated_at=ld.updated_at,
    )


@router.get("", response_model=LabelDefinitionListOut)
def list_labels(
    authorization: str | None = Header(default=None),
    active_only: bool = True,
    db: Session = Depends(get_db),
) -> LabelDefinitionListOut:
    """List label definitions. Any authenticated user can read; admin can see inactive."""
    parse_access_token(authorization)  # just require auth
    q = select(LabelDefinition).order_by(LabelDefinition.name.asc())
    if active_only:
        q = q.where(LabelDefinition.is_active.is_(True))
    items = db.scalars(q).all()
    return LabelDefinitionListOut(items=[_out(x) for x in items])


@router.post("", response_model=LabelDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_label(
    payload: LabelDefinitionCreateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LabelDefinitionOut:
    _ensure_admin(authorization)

    existing = db.scalar(select(LabelDefinition).where(LabelDefinition.code == payload.code))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Label with code '{payload.code}' already exists",
        )

    ld = LabelDefinition(
        code=payload.code,
        name=payload.name,
        kind=LabelKind(payload.kind),
        is_active=True,
    )
    db.add(ld)
    db.commit()
    db.refresh(ld)
    return _out(ld)


@router.patch("/{label_id}", response_model=LabelDefinitionOut)
def update_label(
    label_id: str,
    payload: LabelDefinitionCreateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LabelDefinitionOut:
    _ensure_admin(authorization)
    ld = db.get(LabelDefinition, label_id)
    if not ld:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")

    # check code uniqueness if changed
    if payload.code != ld.code:
        existing = db.scalar(select(LabelDefinition).where(LabelDefinition.code == payload.code))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Label with code '{payload.code}' already exists",
            )

    ld.code = payload.code
    ld.name = payload.name
    ld.kind = LabelKind(payload.kind)
    db.commit()
    db.refresh(ld)
    return _out(ld)


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_label(
    label_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Soft-delete: marks label as inactive rather than deleting it."""
    _ensure_admin(authorization)
    ld = db.get(LabelDefinition, label_id)
    if not ld:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    ld.is_active = False
    db.commit()
