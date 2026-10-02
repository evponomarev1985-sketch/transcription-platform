from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..models import LabelDefinition, LabelRule, LabelRuleDefinition, LabelRuleType
from ..schemas import (
    LabelDefinitionOut,
    LabelRuleCreateRequest,
    LabelRuleListOut,
    LabelRuleOut,
    LabelRuleUpdateRequest,
    ValidatePromptOut,
    ValidatePromptParsed,
    ValidatePromptRequest,
)
from ..security import parse_access_token

router = APIRouter(prefix="/api/v1/calls/label-rules", tags=["label-rules"])
log = logging.getLogger("call-service.label_rules")


# ── helpers ────────────────────────────────────────────────────────────────────


def _ensure_admin(authorization: str | None) -> None:
    payload = parse_access_token(authorization)
    if str(payload.get("role")) != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _auth_payload(authorization: str | None) -> dict:
    return parse_access_token(authorization)


def _is_admin(payload: dict) -> bool:
    return str(payload.get("role")) == "ADMIN"


def _company_scope(payload: dict) -> tuple[str | None, str | None]:
    company_id = str(payload.get("company_id") or "").strip() or None
    company_name = str(payload.get("company_name") or "").strip() or None
    return company_id, company_name


def _rule_list_query_for_payload(payload: dict):
    query = (
        select(LabelRule)
        .where(LabelRule.deleted_at.is_(None))
        .options(selectinload(LabelRule.allowed_label_definitions).selectinload(LabelRuleDefinition.label))
        .order_by(LabelRule.created_at.desc())
    )
    company_id, _ = _company_scope(payload)
    if company_id:
        return query.where(or_(LabelRule.owner_company_id == company_id, LabelRule.owner_company_id.is_(None)))
    if _is_admin(payload):
        return query
    return query.where(LabelRule.owner_company_id.is_(None))


def _ensure_strict_company_rule_access(payload: dict, rule: LabelRule) -> None:
    company_id, _ = _company_scope(payload)
    if company_id:
        if rule.owner_company_id == company_id:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if _is_admin(payload) and rule.owner_company_id is None:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _ensure_label_access_for_company(label_defs: list[LabelDefinition], owner_company_id: str | None) -> None:
    allowed_company_ids: set[str | None] = {None}
    if owner_company_id:
        allowed_company_ids.add(owner_company_id)

    foreign = [ld.id for ld in label_defs if ld.owner_company_id not in allowed_company_ids]
    if foreign:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Selected labels are not available for this company: {foreign}",
        )


def _label_def_out(ld: LabelDefinition) -> LabelDefinitionOut:
    return LabelDefinitionOut(
        id=ld.id,
        code=ld.code,
        name=ld.name,
        kind=ld.kind.value,  # type: ignore[arg-type]
        is_active=ld.is_active,
        created_at=ld.created_at,
        updated_at=ld.updated_at,
    )


def _rule_out(rule: LabelRule) -> LabelRuleOut:
    cfg = json.loads(rule.config_json or "{}")
    owner_company_id = str(rule.owner_company_id or "").strip() or None

    def _label_allowed_for_rule(label: LabelDefinition) -> bool:
        if owner_company_id:
            return label.owner_company_id in {owner_company_id, None}
        return label.owner_company_id is None

    label_defs = [
        _label_def_out(rd.label)
        for rd in sorted(rule.allowed_label_definitions, key=lambda x: x.sort_order)
        if rd.label is not None and _label_allowed_for_rule(rd.label)
    ]
    primary_label = label_defs[0] if label_defs else None
    cfg_kind = str(cfg.get("kind") or "").upper()
    if cfg_kind in {"FLAG", "FLAG_VALUE", "COMMENT"}:
        resolved_kind = cfg_kind
    elif primary_label:
        resolved_kind = primary_label.kind
    else:
        resolved_kind = "FLAG"
    return LabelRuleOut(
        id=rule.id,
        name=rule.name,
        rule_type=rule.rule_type.value,  # type: ignore[arg-type]
        is_enabled=rule.is_enabled,
        kind=resolved_kind,  # type: ignore[arg-type]
        label_ids=[ld.id for ld in label_defs],
        labels=label_defs,
        keyword_query=cfg.get("query"),
        keyword_search_part=cfg.get("search_part"),  # type: ignore[arg-type]
        llm_prompt=cfg.get("prompt"),
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _load_rule_with_labels(db: Session, rule_id: str) -> LabelRule | None:
    return db.execute(
        select(LabelRule)
        .where(LabelRule.id == rule_id, LabelRule.deleted_at.is_(None))
        .options(selectinload(LabelRule.allowed_label_definitions).selectinload(LabelRuleDefinition.label))
    ).scalar_one_or_none()


def _resolve_label_ids(db: Session, label_ids: list[str]) -> list[LabelDefinition]:
    """Fetch LabelDefinitions by id list, raise 422 if any missing."""
    if not label_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one label is required",
        )
    normalized_label_ids: list[str] = []
    for label_id in label_ids:
        try:
            normalized_label_ids.append(str(UUID(label_id)))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid label id format: {label_id}",
            ) from exc

    defs = db.scalars(select(LabelDefinition).where(LabelDefinition.id.in_(normalized_label_ids))).all()
    found = {d.id for d in defs}
    missing = [lid for lid in normalized_label_ids if lid not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Label definitions not found: {missing}",
        )
    return list(defs)


def _validate_labels_for_rule(label_defs: list[LabelDefinition]) -> None:
    """Business rules for allowed labels count and kind consistency."""
    if not label_defs:
        return

    kinds = {d.kind.value for d in label_defs}
    if len(kinds) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All labels in a rule must have the same kind",
        )

    only_kind = next(iter(kinds))
    if only_kind == "FLAG_VALUE" and len(label_defs) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="FLAG_VALUE kind requires exactly one label per rule",
        )
    if only_kind == "COMMENT" and len(label_defs) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="COMMENT kind allows at most one label per rule",
        )


def _build_config(payload: LabelRuleCreateRequest | LabelRuleUpdateRequest, rule_type: LabelRuleType) -> dict:
    if rule_type == LabelRuleType.KEYWORD:
        query = (getattr(payload, "keyword_query", None) or "").strip()
        if not query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="keyword_query is required for KEYWORD rule",
            )
        search_part = getattr(payload, "keyword_search_part", None) or "ANY"
        return {
            "query": query,
            "search_part": search_part,
        }
    prompt = (getattr(payload, "llm_prompt", None) or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="llm_prompt is required for LLM rule",
        )
    kind = str(getattr(payload, "kind", "") or "").strip().upper()
    return {"prompt": prompt, "kind": kind}


def _ensure_payload_kind_matches_labels(payload_kind: str, label_defs: list[LabelDefinition]) -> None:
    if not label_defs:
        if payload_kind == "COMMENT":
            return
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Payload kind '{payload_kind}' requires at least one label",
        )

    mismatched = [ld.id for ld in label_defs if ld.kind.value != payload_kind]
    if mismatched:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Payload kind '{payload_kind}' does not match selected labels: {mismatched}",
        )


def _rule_kind_from_config_or_labels(rule: LabelRule) -> str:
    cfg = json.loads(rule.config_json or "{}")
    cfg_kind = str(cfg.get("kind") or "").upper()
    if cfg_kind in {"FLAG", "FLAG_VALUE", "COMMENT"}:
        return cfg_kind
    if rule.allowed_label_definitions:
        return rule.allowed_label_definitions[0].label.kind.value
    return "FLAG"


def _resolve_rule_kind_for_request(
    payload_kind: str | None,
    label_defs: list[LabelDefinition],
) -> str:
    kind = str(payload_kind or "").strip().upper()
    if kind in {"FLAG", "FLAG_VALUE", "COMMENT"}:
        return kind
    if label_defs:
        return label_defs[0].kind.value
    return "FLAG"


def _set_allowed_labels(
    db: Session, rule: LabelRule, label_defs: list[LabelDefinition]
) -> None:
    """Replace the rule's allowed_label_definitions with the given list."""
    # delete existing
    db.query(LabelRuleDefinition).filter(LabelRuleDefinition.rule_id == rule.id).delete()
    db.flush()
    for idx, ld in enumerate(label_defs):
        db.add(LabelRuleDefinition(rule_id=rule.id, label_id=ld.id, sort_order=idx))
    # set primary label_id to first in list
    rule.label_id = label_defs[0].id if label_defs else None
    # keep legacy non-null label_value compatibility in existing databases
    if label_defs:
        rule.label_value = label_defs[0].name
    elif _rule_kind_from_config_or_labels(rule) == "COMMENT":
        rule.label_value = rule.name
    else:
        rule.label_value = ""


def _extract_expected_text_values_from_prompt(prompt_text: str) -> list[str]:
    values: list[str] = []

    # 1) Parse bracket format: [A / B / C]
    for match in re.finditer(r"\[(.*?)\]", prompt_text, flags=re.DOTALL):
        raw = match.group(1)
        parts = [p.strip() for p in re.split(r"\s*/\s*", raw) if p.strip()]
        # ignore non-choice brackets
        if len(parts) >= 2 and all(len(p) <= 64 for p in parts):
            values.extend(parts)

    # 2) Parse bullet lines: - Value
    bullet_parts: list[str] = []
    for line in prompt_text.splitlines():
        m = re.match(r"^\s*[-•]\s+(.+?)\s*$", line)
        if not m:
            continue
        val = m.group(1).strip()
        if val and len(val) <= 64:
            bullet_parts.append(val)
    if len(bullet_parts) >= 2:
        values.extend(bullet_parts)

    # 3) Parse quoted pair format: "A" или "B" / «A» или «B»
    for match in re.finditer(r'["«]([^"»]{1,64})["»]\s*(?:/|или|or)\s*["«]([^"»]{1,64})["»]', prompt_text, flags=re.IGNORECASE):
        left = match.group(1).strip()
        right = match.group(2).strip()
        if left and right:
            values.extend([left, right])

    # 4) Parse separate quoted binary options like «присутствует» ... «отсутствует»
    quoted_tokens = [q.strip() for q in re.findall(r'["«]([^"»]{1,64})["»]', prompt_text) if q and q.strip()]
    present_markers = ("присутств", "present")
    absent_markers = ("отсутств", "absent")
    present_q = next((q for q in quoted_tokens if any(m in q.casefold() for m in present_markers)), None)
    absent_q = next((q for q in quoted_tokens if any(m in q.casefold() for m in absent_markers)), None)
    if present_q and absent_q:
        values.extend([present_q, absent_q])

    # unique preserving order
    uniq: list[str] = []
    seen: set[str] = set()
    for v in values:
        key = v.casefold()
        if key not in seen:
            seen.add(key)
            uniq.append(v)
    return uniq


def _coerce_matched_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "да", "matched", "присутствует", "present"}:
        return True
    if text in {"false", "0", "no", "нет", "absent", "отсутствует", "not_matched"}:
        return False
    return False


def _normalize_value_text(raw: object) -> str | None:
    text = str(raw or "").strip()
    return text or None


def _is_flag_value_allowed(value_text: str | None, allowed_values: list[str]) -> bool:
    if not value_text:
        return False
    allowed = {v.strip().casefold() for v in allowed_values if str(v).strip()}
    if not allowed:
        return False
    return value_text.strip().casefold() in allowed


def _has_extracted_value(*, value_text: str | None) -> bool:
    return bool(str(value_text or "").strip())


def _recover_flag_value_text(
    prompt_text: str,
    matched: bool,
    comment: str | None,
    raw_value_text: str | None,
) -> str | None:
    current = str(raw_value_text or "").strip()
    if current:
        return current

    expected_values = _extract_expected_text_values_from_prompt(prompt_text)
    prompt_cf = str(prompt_text or "").casefold()

    direct_present = "присутствует" if "присутствует" in prompt_cf else ("present" if "present" in prompt_cf else None)
    direct_absent = "отсутствует" if "отсутствует" in prompt_cf else ("absent" if "absent" in prompt_cf else None)

    if not expected_values:
        if matched and direct_present:
            return direct_present
        if not matched and direct_absent:
            return direct_absent
        return None

    comment_cf = str(comment or "").casefold()
    if comment_cf:
        for option in expected_values:
            if option.casefold() in comment_cf:
                return option

    absent_markers = ("отсутств", "не выяв", "нет", "absent", "no")
    present_markers = ("присутств", "выяв", "есть", "present", "yes")

    absent_candidate = next(
        (opt for opt in expected_values if any(marker in opt.casefold() for marker in absent_markers)),
        None,
    )
    present_candidate = next(
        (opt for opt in expected_values if any(marker in opt.casefold() for marker in present_markers)),
        None,
    )

    if matched and present_candidate:
        return present_candidate
    if not matched and absent_candidate:
        return absent_candidate

    if matched and direct_present:
        return direct_present
    if not matched and direct_absent:
        return direct_absent

    if len(expected_values) == 1:
        return expected_values[0]
    return None


def _resolve_rule_kind_for_validate(
    db: Session,
    kind_hint: str | None,
    label_id_hint: str | None,
) -> tuple[str, str | None, LabelDefinition | None]:
    kind = str(kind_hint or "").strip().upper()
    label_id = str(label_id_hint or "").strip() if label_id_hint is not None else None

    if label_id:
        try:
            normalized_label_id = str(UUID(label_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid label id format: {label_id}",
            ) from exc

        label_def = db.get(LabelDefinition, normalized_label_id)
        if not label_def:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Label not found: {normalized_label_id}",
            )

        resolved_kind = kind if kind in {"FLAG", "FLAG_VALUE", "COMMENT"} else label_def.kind.value
        return resolved_kind, normalized_label_id, label_def

    if kind in {"FLAG", "FLAG_VALUE", "COMMENT"}:
        return kind, None, None

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Either valid label_id or kind must be provided",
    )


def _parse_llm_json_object(raw_text: str) -> dict | None:
    clean = raw_text.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        clean = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])

    try:
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    first = clean.find("{")
    if first == -1:
        return None

    tail = clean[first:]
    # If model forgot trailing braces, close them.
    missing_closing = max(0, tail.count("{") - tail.count("}"))
    candidate = tail + ("}" * missing_closing)

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


# ── IAM token for validate-prompt ─────────────────────────────────────────────


def _get_iam_token() -> str:
    s = get_settings()
    if s.yc_iam_token_source.lower() == "env":
        if not s.yc_iam_token:
            raise ValueError("YC_IAM_TOKEN is required when YC_IAM_TOKEN_SOURCE=env")
        return s.yc_iam_token
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            s.yc_metadata_token_url,
            headers={"Metadata-Flavor": "Google"},
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=LabelRuleListOut)
def list_rules(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LabelRuleListOut:
    payload = _auth_payload(authorization)
    if not _is_admin(payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    rules = db.scalars(_rule_list_query_for_payload(payload)).all()
    return LabelRuleListOut(items=[_rule_out(r) for r in rules])


@router.post("", response_model=LabelRuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: LabelRuleCreateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LabelRuleOut:
    auth_payload = _auth_payload(authorization)
    if not _is_admin(auth_payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    owner_company_id, owner_company_name = _company_scope(auth_payload)
    if not owner_company_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Company context is required")
    if payload.kind == "COMMENT":
        label_defs: list[LabelDefinition] = []
    else:
        if not payload.label_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one label is required")
        label_defs = _resolve_label_ids(db, payload.label_ids)
        _ensure_label_access_for_company(label_defs, owner_company_id)
    _validate_labels_for_rule(label_defs)
    _ensure_payload_kind_matches_labels(payload.kind, label_defs)
    effective_kind = _resolve_rule_kind_for_request(payload.kind, label_defs)
    cfg = _build_config(payload, LabelRuleType(payload.rule_type))
    cfg["kind"] = effective_kind

    rule = LabelRule(
        name=payload.name,
        owner_company_id=owner_company_id,
        owner_company_name=owner_company_name,
        # keep legacy non-null label_value compatibility in existing databases
        label_value=(label_defs[0].name if label_defs else (payload.name if effective_kind == "COMMENT" else "")),
        rule_type=LabelRuleType(payload.rule_type),
        is_enabled=payload.is_enabled,
        config_json=json.dumps(cfg, ensure_ascii=False),
        label_id=label_defs[0].id if label_defs else None,
    )
    db.add(rule)
    db.flush()  # get rule.id

    for idx, ld in enumerate(label_defs):
        db.add(LabelRuleDefinition(rule_id=rule.id, label_id=ld.id, sort_order=idx))

    db.commit()
    rule = _load_rule_with_labels(db, rule.id)
    return _rule_out(rule)  # type: ignore[arg-type]


@router.patch("/{rule_id}", response_model=LabelRuleOut)
def update_rule(
    rule_id: str,
    payload: LabelRuleUpdateRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LabelRuleOut:
    payload_auth = _auth_payload(authorization)
    if not _is_admin(payload_auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    rule = _load_rule_with_labels(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    _ensure_strict_company_rule_access(payload_auth, rule)

    existing_kind = _rule_kind_from_config_or_labels(rule)

    if payload.name is not None:
        rule.name = payload.name
    if payload.is_enabled is not None:
        rule.is_enabled = payload.is_enabled

    cfg = json.loads(rule.config_json or "{}")
    if rule.rule_type == LabelRuleType.KEYWORD:
        if payload.keyword_query is not None:
            cfg["query"] = payload.keyword_query.strip()
        if payload.keyword_search_part is not None:
            cfg["search_part"] = payload.keyword_search_part
        if not str(cfg.get("query", "")).strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="keyword_query is required for KEYWORD rule",
            )
    else:
        if payload.llm_prompt is not None:
            cfg["prompt"] = payload.llm_prompt.strip()
        if not str(cfg.get("prompt", "")).strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="llm_prompt is required for LLM rule",
            )

    cfg["kind"] = existing_kind
    rule.config_json = json.dumps(cfg, ensure_ascii=False)

    if payload.label_ids is not None:
        if not payload.label_ids:
            if existing_kind == "COMMENT":
                _set_allowed_labels(db, rule, [])
            else:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one label is required")
        else:
            label_defs = _resolve_label_ids(db, payload.label_ids)
            owner_company_id = str(rule.owner_company_id or "").strip() or None
            _ensure_label_access_for_company(label_defs, owner_company_id)
            _validate_labels_for_rule(label_defs)
            primary_kind = label_defs[0].kind.value if label_defs else None
            if primary_kind and primary_kind != existing_kind:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Rule kind is '{existing_kind}', got labels with kind '{primary_kind}'",
                )
            _set_allowed_labels(db, rule, label_defs)
    elif existing_kind == "COMMENT" and not rule.allowed_label_definitions:
        rule.label_value = rule.name

    db.commit()
    rule = _load_rule_with_labels(db, rule_id)
    return _rule_out(rule)  # type: ignore[arg-type]


@router.patch("/{rule_id}/toggle", response_model=LabelRuleOut)
def toggle_rule(
    rule_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LabelRuleOut:
    payload = _auth_payload(authorization)
    if not _is_admin(payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    rule = _load_rule_with_labels(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    _ensure_strict_company_rule_access(payload, rule)
    rule.is_enabled = not rule.is_enabled
    db.commit()
    rule = _load_rule_with_labels(db, rule_id)
    return _rule_out(rule)  # type: ignore[arg-type]


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    payload = _auth_payload(authorization)
    if not _is_admin(payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    rule = _load_rule_with_labels(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    _ensure_strict_company_rule_access(payload, rule)
    rule.is_enabled = False
    rule.deleted_at = datetime.now(UTC)
    db.commit()


@router.post("/validate-prompt", response_model=ValidatePromptOut)
def validate_prompt(
    payload: ValidatePromptRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ValidatePromptOut:
    """Call YandexGPT with sample transcript and check response format."""
    payload_auth = _auth_payload(authorization)
    if not _is_admin(payload_auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    kind, label_id, label_def = _resolve_rule_kind_for_validate(db, payload.kind, payload.label_id)
    owner_company_id, _ = _company_scope(payload_auth)
    if label_def:
        _ensure_label_access_for_company([label_def], owner_company_id)

    allowed_values_for_flag: list[str] = [label_def.name] if label_def else []
    if kind == "FLAG" and payload.label_ids:
        normalized_ids: list[str] = []
        for lid in payload.label_ids:
            try:
                normalized_ids.append(str(UUID(lid)))
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid label id format in label_ids: {lid}",
                ) from exc
        defs = db.scalars(select(LabelDefinition).where(LabelDefinition.id.in_(normalized_ids))).all()
        _ensure_label_access_for_company(list(defs), owner_company_id)
        if defs:
            allowed_values_for_flag = [d.name for d in defs]
    if kind == "FLAG" and not allowed_values_for_flag:
        return ValidatePromptOut(valid=False, message="For FLAG validation provide label_id or label_ids")

    allowed_values_line = ""
    if kind == "FLAG" and allowed_values_for_flag:
        allowed_values_line = (
            f"Если matched=true, value_text должен быть одним из allowed_values: {allowed_values_for_flag}. "
            f"Не придумывай значения вне списка.\n"
        )

    instruction = (
        "Ты анализируешь транскрипт строго по пользовательскому правилу.\n"
        "Не переопределяй и не дополняй правило своими критериями.\n"
        f"kind: {kind}\n"
        f"user_rule: {payload.prompt_text}\n"
        "rule_id: validate\n"
        "Верни ТОЛЬКО валидный JSON без markdown и пояснений.\n"
        "Допустимые поля ответа: matched, value_text, comment, rule_id.\n"
        "Формат JSON: "
        '{"rule_id":"validate","matched":true/false,"value_text":string|null,"comment":string|null}\n'
        "Требования:\n"
        "- JSON должен быть валидным.\n"
        "- Если по правилу нет срабатывания: matched=false.\n"
        "- Если matched=true, заполни comment кратко.\n"
        "- Не добавляй поля, которых нет в контракте.\n"
        f"{allowed_values_line}"
        "- rule_id должен быть равен validate.\n"
    )

    full_prompt = f"{instruction}\n\nТранскрипт:\n{payload.test_text[:4000]}"

    s = get_settings()
    if not s.yandexgpt_model_uri and not s.yandexgpt_folder_id:
        return ValidatePromptOut(
            valid=False,
            message="YANDEXGPT_MODEL_URI or YANDEXGPT_FOLDER_ID not configured on server",
        )

    model_uri = s.yandexgpt_model_uri or f"gpt://{s.yandexgpt_folder_id}/yandexgpt-lite/latest"

    try:
        iam_token = _get_iam_token()
    except Exception as exc:
        return ValidatePromptOut(valid=False, message=f"Failed to obtain IAM token: {exc}")

    body = {
        "modelUri": model_uri,
        "completionOptions": {"stream": False, "temperature": 0.1, "maxTokens": 512},
        "messages": [
            {"role": "system", "text": "Ты помощник для анализа звонков. Отвечай строго JSON."},
            {"role": "user", "text": full_prompt},
        ],
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                s.yandexgpt_api_url,
                json=body,
                headers={
                    "Authorization": f"Bearer {iam_token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code >= 400:
                log.error("YandexGPT validate-prompt failed status=%s body=%s", resp.status_code, resp.text[:800])
                return ValidatePromptOut(
                    valid=False,
                    message=f"YandexGPT API error {resp.status_code}: {resp.text[:300]}",
                )
            data = resp.json()
    except Exception as exc:
        return ValidatePromptOut(valid=False, message=f"YandexGPT request failed: {exc}")

    try:
        raw_text = data["result"]["alternatives"][0]["message"]["text"]
    except (KeyError, IndexError, TypeError):
        return ValidatePromptOut(valid=False, message="Unexpected YandexGPT response structure")

    parsed = _parse_llm_json_object(raw_text)
    if not parsed:
        return ValidatePromptOut(valid=False, message=f"LLM did not return valid JSON. Got: {raw_text[:300]}")

    unexpected_fields = sorted(set(parsed.keys()) - {"rule_id", "matched", "value_text", "comment"})
    if unexpected_fields:
        return ValidatePromptOut(
            valid=False,
            message=f"LLM returned unsupported fields: {unexpected_fields}. Allowed fields: matched, value_text, comment, rule_id",
        )

    returned_rule_id = str(parsed.get("rule_id") or "").strip()
    if returned_rule_id and returned_rule_id != "validate":
        return ValidatePromptOut(valid=False, message=f"rule_id must be 'validate', got '{returned_rule_id}'")

    # Runtime-compatible extraction logic (same semantics as transcription-service pipeline)
    matched_flag = _coerce_matched_flag(parsed.get("matched", False))
    parsed_value_text = _normalize_value_text(parsed.get("value_text"))

    if "matched" not in parsed:
        return ValidatePromptOut(valid=False, message="Missing required field: matched")

    parsed_comment = str(parsed.get("comment") or "").strip() or None

    if kind == "FLAG_VALUE":
        parsed_value_text = _recover_flag_value_text(
            prompt_text=payload.prompt_text,
            matched=matched_flag,
            comment=parsed_comment,
            raw_value_text=parsed_value_text,
        )
        matched_flag = _has_extracted_value(value_text=parsed_value_text)

    if kind == "FLAG":
        if matched_flag and not _is_flag_value_allowed(parsed_value_text, allowed_values_for_flag):
            matched_flag = False
            if not parsed_comment:
                parsed_comment = "Значение не соответствует выбранным меткам правила"

    if kind == "COMMENT" and not parsed_comment:
        return ValidatePromptOut(valid=False, message="Missing or empty field: comment")

    parsed_obj = ValidatePromptParsed(
        kind=kind,  # type: ignore[arg-type]
        label_id=label_id,
        matched=matched_flag,
        value_text=parsed_value_text,
        comment=parsed_comment,
    )
    return ValidatePromptOut(
        valid=True,
        message="Prompt is valid",
        parsed=parsed_obj,
    )
