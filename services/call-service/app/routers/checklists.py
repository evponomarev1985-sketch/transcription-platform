from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CallLabelResult, Checklist, LabelDefinition, LabelKind
from ..schemas import (
    ChecklistCreateRequest,
    ChecklistLabelValueOptionOut,
    ChecklistLabelValuesOut,
    ChecklistListOut,
    ChecklistOut,
    ChecklistUpdateRequest,
)
from ..security import parse_access_token


router = APIRouter(prefix="/api/v1/checklists", tags=["checklists"])


def _ensure_admin(authorization: str | None) -> None:
    payload = parse_access_token(authorization)
    if str(payload.get("role")) != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _ensure_auth(authorization: str | None) -> None:
    parse_access_token(authorization)


def _collect_label_refs_from_lines(lines: list[dict]) -> set[str]:
    refs: set[str] = set()
    for line in lines:
        if not isinstance(line, dict):
            continue
        for target in (line.get("targets") or []):
            if not isinstance(target, dict):
                continue
            label_id = str(target.get("label_id") or "").strip()
            if label_id:
                refs.add(label_id)
    return refs


def _normalize_target(raw_target: dict) -> dict:
    label_id = str(raw_target.get("label_id") or "").strip()
    raw_values = raw_target.get("values")
    values: list[str] = []
    if isinstance(raw_values, list):
        values = [str(v).strip() for v in raw_values if str(v).strip()]
    elif raw_target.get("value") is not None and str(raw_target.get("value") or "").strip():
        values = [str(raw_target.get("value") or "").strip()]
    return {
        "label_id": label_id,
        "values": values,
        "value": values[0] if values else None,
    }


def _normalize_line(raw_line: dict) -> dict:
    targets = [_normalize_target(t) for t in (raw_line.get("targets") or []) if isinstance(t, dict)]
    targets = [t for t in targets if t.get("label_id")]
    return {
        "operator": str(raw_line.get("operator") or "").upper(),
        "targets": targets,
    }


def _normalize_apply_filters(raw_lines: list[dict]) -> list[dict]:
    normalized = [_normalize_line(line) for line in raw_lines if isinstance(line, dict)]
    return [line for line in normalized if line.get("targets")]


def _normalize_answer_conditions(raw_lines: list[dict], label_kind_by_id: dict[str, str]) -> list[dict]:
    normalized = _normalize_apply_filters(raw_lines)
    for line in normalized:
        for target in line.get("targets", []):
            label_id = str(target.get("label_id") or "")
            kind = label_kind_by_id.get(label_id)
            if kind == "FLAG_VALUE" and not target.get("values"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="For FLAG_VALUE labels, selecting at least one value is required",
                )
    return normalized


def _enforce_required_values_for_flag_value(lines: list[dict], label_kind_by_id: dict[str, str]) -> None:
    for line in lines:
        for target in line.get("targets", []):
            label_id = str(target.get("label_id") or "")
            kind = label_kind_by_id.get(label_id)
            if kind == "FLAG_VALUE" and not target.get("values"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="For FLAG_VALUE labels, selecting at least one value is required",
                )


def _validate_checklist_config(db: Session, *, apply_filters: list[dict], questions: list[dict]) -> None:
    label_ids: set[str] = set(_collect_label_refs_from_lines(apply_filters))
    for question in questions:
        answers = question.get("answers") or []
        for answer in answers:
            label_ids |= _collect_label_refs_from_lines(answer.get("conditions") or [])

    if not label_ids:
        return

    existing = db.scalars(select(LabelDefinition.id).where(LabelDefinition.id.in_(list(label_ids)))).all()
    found = set(existing)
    missing = sorted(label_ids - found)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown label ids in checklist conditions: {missing}",
        )


def _label_kind_by_id_map(db: Session, label_ids: set[str]) -> dict[str, str]:
    if not label_ids:
        return {}
    defs = db.scalars(select(LabelDefinition).where(LabelDefinition.id.in_(list(label_ids)))).all()
    return {d.id: d.kind.value for d in defs}


def _normalize_questions(questions: list[dict]) -> list[dict]:
    # NOTE: conditions are normalized in create/update where label kinds are known.
    normalized: list[dict] = []
    for q in questions:
        qid = str(q.get("id") or "").strip() or f"q_{len(normalized) + 1}"
        normalized.append({**q, "id": qid})
    return normalized


def _normalize_questions_with_conditions(db: Session, questions: list[dict], apply_filters: list[dict]) -> list[dict]:
    label_ids: set[str] = set(_collect_label_refs_from_lines(apply_filters))
    for q in questions:
        for answer in (q.get("answers") or []):
            label_ids |= _collect_label_refs_from_lines(answer.get("conditions") or [])
    kind_map = _label_kind_by_id_map(db, label_ids)
    _enforce_required_values_for_flag_value(apply_filters, kind_map)

    normalized_questions: list[dict] = []
    for q in _normalize_questions(questions):
        answers_out: list[dict] = []
        for answer in (q.get("answers") or []):
            answers_out.append(
                {
                    **answer,
                    "conditions": _normalize_answer_conditions(answer.get("conditions") or [], kind_map),
                }
            )
        normalized_questions.append({**q, "answers": answers_out})
    return normalized_questions


def _out(checklist: Checklist) -> ChecklistOut:
    cfg = json.loads(checklist.config_json or "{}")
    return ChecklistOut(
        id=checklist.id,
        name=checklist.name,
        description=checklist.description,
        is_active=checklist.is_active,
        apply_filters=cfg.get("apply_filters") or [],
        questions=cfg.get("questions") or [],
        created_at=checklist.created_at,
        updated_at=checklist.updated_at,
    )


@router.get("", response_model=ChecklistListOut)
def list_checklists(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ChecklistListOut:
    _ensure_auth(authorization)
    items = db.scalars(select(Checklist).order_by(Checklist.created_at.desc())).all()
    return ChecklistListOut(items=[_out(x) for x in items])


@router.get("/label-values", response_model=ChecklistLabelValuesOut)
def checklist_label_values(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ChecklistLabelValuesOut:
    _ensure_auth(authorization)
    defs = db.scalars(select(LabelDefinition).where(LabelDefinition.is_active.is_(True))).all()

    items: dict[str, list[ChecklistLabelValueOptionOut]] = {}
    for ld in defs:
        values_counter: dict[str, int] = {}
        rows = db.scalars(
            select(CallLabelResult)
            .where(CallLabelResult.label_id == ld.id, CallLabelResult.matched.is_(True))
            .order_by(CallLabelResult.evaluated_at.desc())
            .limit(5000)
        ).all()

        if ld.kind == LabelKind.FLAG:
            values_counter[ld.name] = len(rows)
        else:
            for row in rows:
                val = ""
                if row.value_text is not None and str(row.value_text).strip():
                    val = str(row.value_text).strip()
                elif row.value_number is not None:
                    n = float(row.value_number)
                    val = str(int(n)) if n == int(n) else str(n)
                if not val:
                    continue
                values_counter[val] = values_counter.get(val, 0) + 1

        options = [
            ChecklistLabelValueOptionOut(value=value, usage_count=count)
            for value, count in sorted(values_counter.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        items[ld.id] = options

    return ChecklistLabelValuesOut(items=items)


@router.post("", response_model=ChecklistOut, status_code=status.HTTP_201_CREATED)
def create_checklist(
    payload: ChecklistCreateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ChecklistOut:
    _ensure_admin(authorization)
    apply_filters = _normalize_apply_filters([x.model_dump() for x in payload.apply_filters])
    questions = _normalize_questions_with_conditions(db, [x.model_dump() for x in payload.questions], apply_filters)
    _validate_checklist_config(db, apply_filters=apply_filters, questions=questions)

    checklist = Checklist(
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
        config_json=json.dumps({"apply_filters": apply_filters, "questions": questions}, ensure_ascii=False),
    )
    db.add(checklist)
    db.commit()
    db.refresh(checklist)
    return _out(checklist)


@router.patch("/{checklist_id}", response_model=ChecklistOut)
def update_checklist(
    checklist_id: str,
    payload: ChecklistUpdateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ChecklistOut:
    _ensure_admin(authorization)
    checklist = db.get(Checklist, checklist_id)
    if not checklist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist not found")

    cfg = json.loads(checklist.config_json or "{}")
    apply_filters = cfg.get("apply_filters") or []
    questions = cfg.get("questions") or []

    if payload.name is not None:
        checklist.name = payload.name
    if payload.description is not None:
        checklist.description = payload.description
    if payload.is_active is not None:
        checklist.is_active = payload.is_active
    if payload.apply_filters is not None:
        apply_filters = _normalize_apply_filters([x.model_dump() for x in payload.apply_filters])
    if payload.questions is not None:
        questions = _normalize_questions_with_conditions(db, [x.model_dump() for x in payload.questions], apply_filters)

    _validate_checklist_config(db, apply_filters=apply_filters, questions=questions)
    checklist.config_json = json.dumps({"apply_filters": apply_filters, "questions": questions}, ensure_ascii=False)

    db.commit()
    db.refresh(checklist)
    return _out(checklist)


@router.delete("/{checklist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist(
    checklist_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _ensure_admin(authorization)
    checklist = db.get(Checklist, checklist_id)
    if not checklist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist not found")
    db.delete(checklist)
    db.commit()
