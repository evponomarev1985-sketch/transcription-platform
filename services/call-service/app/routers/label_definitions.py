from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LabelDefinition, LabelKind
from ..schemas import LabelDefinitionCreateRequest, LabelDefinitionListOut, LabelDefinitionOut
from ..security import parse_access_token

router = APIRouter(prefix="/api/v1/calls/labels", tags=["label-definitions"])


def _auth_payload(authorization: str | None) -> dict:
    return parse_access_token(authorization)


def _is_admin(payload: dict) -> bool:
    return str(payload.get("role")) == "ADMIN"


def _company_scope(payload: dict) -> tuple[str | None, str | None]:
    company_id = str(payload.get("company_id") or "").strip() or None
    company_name = str(payload.get("company_name") or "").strip() or None
    return company_id, company_name


def _ensure_admin(payload: dict) -> None:
    if not _is_admin(payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _label_list_query_for_payload(payload: dict, *, active_only: bool):
    query = select(LabelDefinition).order_by(LabelDefinition.name.asc())
    if active_only:
        query = query.where(LabelDefinition.is_active.is_(True))

    company_id, _ = _company_scope(payload)
    if company_id:
        return query.where(or_(LabelDefinition.owner_company_id == company_id, LabelDefinition.owner_company_id.is_(None)))
    return query.where(LabelDefinition.owner_company_id.is_(None))


def _ensure_strict_company_label_access(payload: dict, label: LabelDefinition) -> None:
    company_id, _ = _company_scope(payload)
    if company_id:
        if label.owner_company_id == company_id:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if _is_admin(payload) and label.owner_company_id is None:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _same_company_code_exists(
    db: Session,
    *,
    code: str,
    owner_company_id: str | None,
    exclude_id: str | None = None,
) -> bool:
    query = select(LabelDefinition).where(LabelDefinition.code == code)
    if owner_company_id is None:
        query = query.where(LabelDefinition.owner_company_id.is_(None))
    else:
        query = query.where(LabelDefinition.owner_company_id == owner_company_id)
    if exclude_id:
        query = query.where(LabelDefinition.id != exclude_id)
    return db.scalar(query) is not None


def _same_company_name_exists(
    db: Session,
    *,
    name: str,
    owner_company_id: str | None,
    exclude_id: str | None = None,
) -> bool:
    query = select(LabelDefinition).where(LabelDefinition.name == name)
    if owner_company_id is None:
        query = query.where(LabelDefinition.owner_company_id.is_(None))
    else:
        query = query.where(LabelDefinition.owner_company_id == owner_company_id)
    if exclude_id:
        query = query.where(LabelDefinition.id != exclude_id)
    return db.scalar(query) is not None


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
    """List label definitions for current company scope (plus legacy global labels)."""
    payload = _auth_payload(authorization)
    q = _label_list_query_for_payload(payload, active_only=active_only)
    items = db.scalars(q).all()
    return LabelDefinitionListOut(items=[_out(x) for x in items])


@router.post("", response_model=LabelDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_label(
    payload: LabelDefinitionCreateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LabelDefinitionOut:
    auth_payload = _auth_payload(authorization)
    _ensure_admin(auth_payload)
    owner_company_id, owner_company_name = _company_scope(auth_payload)
    if not owner_company_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Company context is required")

    if _same_company_code_exists(db, code=payload.code, owner_company_id=owner_company_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Label with code '{payload.code}' already exists for this company",
        )
    if _same_company_name_exists(db, name=payload.name, owner_company_id=owner_company_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Label with name '{payload.name}' already exists for this company",
        )

    ld = LabelDefinition(
        owner_company_id=owner_company_id,
        owner_company_name=owner_company_name,
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
    auth_payload = _auth_payload(authorization)
    _ensure_admin(auth_payload)
    ld = db.get(LabelDefinition, label_id)
    if not ld:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    _ensure_strict_company_label_access(auth_payload, ld)

    owner_company_id = str(ld.owner_company_id or "").strip() or None

    # check code uniqueness if changed
    if payload.code != ld.code:
        if _same_company_code_exists(db, code=payload.code, owner_company_id=owner_company_id, exclude_id=ld.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Label with code '{payload.code}' already exists for this company",
            )
    if payload.name != ld.name:
        if _same_company_name_exists(db, name=payload.name, owner_company_id=owner_company_id, exclude_id=ld.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Label with name '{payload.name}' already exists for this company",
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
    auth_payload = _auth_payload(authorization)
    _ensure_admin(auth_payload)
    ld = db.get(LabelDefinition, label_id)
    if not ld:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    _ensure_strict_company_label_access(auth_payload, ld)
    ld.is_active = False
    db.commit()
