"""Apply label rules to a completed call and persist results to call_label_results."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
    Call,
    CallLabel,
    CallLabelResult,
    LabelDefinition,
    LabelKind,
    LabelRule,
    LabelRuleDefinition,
    LabelRuleType,
    TranscriptSegment,
)

log = logging.getLogger("call-service.labeling")


# ── text helpers ──────────────────────────────────────────────────────────────


def _segment_text_for_part(segments: Sequence[TranscriptSegment], search_part: str) -> str:
    if not segments:
        return ""
    items = sorted(segments, key=lambda x: x.segment_order)
    n = len(items)
    if search_part == "OPENING":
        window = items[: max(1, n // 3)]
    elif search_part == "MIDDLE":
        start = n // 3
        end = max(start + 1, (2 * n) // 3)
        window = items[start:end]
    elif search_part == "CLOSING":
        window = items[max(0, (2 * n) // 3) :]
    else:
        window = items
    return " ".join(seg.text for seg in window)


def _keyword_match(query: str, text: str) -> bool:
    terms = [t.strip().lower() for t in re.split(r"[,;\n]", query) if t.strip()]
    if not terms:
        return False
    hay = text.lower()
    return any(term in hay for term in terms)


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


def _has_extracted_value(*, value_number: float | None, value_text: str | None) -> bool:
    return value_number is not None or bool(str(value_text or "").strip())


def _rule_scope_filter_for_call(owner_company_id: str | None):
    if owner_company_id:
        return or_(LabelRule.owner_company_id == owner_company_id, LabelRule.owner_company_id.is_(None))
    return LabelRule.owner_company_id.is_(None)


def _label_scope_filter_for_call(owner_company_id: str | None):
    if owner_company_id:
        return or_(LabelDefinition.owner_company_id == owner_company_id, LabelDefinition.owner_company_id.is_(None))
    return LabelDefinition.owner_company_id.is_(None)


def _label_allowed_for_call(label: LabelDefinition | None, owner_company_id: str | None) -> bool:
    if label is None:
        return False
    if owner_company_id:
        return label.owner_company_id in {owner_company_id, None}
    return label.owner_company_id is None


# ── upsert helpers ────────────────────────────────────────────────────────────


def _upsert_result(
    db: Session,
    *,
    call_id: str,
    rule: LabelRule,
    label: LabelDefinition | None,
    matched: bool,
    value_number: float | None = None,
    value_text: str | None = None,
    comment_text: str | None = None,
) -> None:
    label_id = label.id if label else None
    comment_title_snapshot: str | None = None
    rule_kind = ""
    try:
        cfg = json.loads(rule.config_json or "{}")
        rule_kind = str(cfg.get("kind") or "").strip().upper()
    except Exception:
        rule_kind = ""

    # FLAG_VALUE is type-agnostic now: if textual value arrived, do not force numeric projection.
    # Keep value_number only when no textual counterpart is present.
    if value_text is not None and str(value_text).strip() != "":
        value_number = None

    if (label and label.kind == LabelKind.COMMENT) or rule_kind == "COMMENT":
        comment_title_snapshot = rule.name

    if rule_kind == "FLAG" and matched and label and value_text:
        actual = str(value_text).strip().casefold()
        expected = str(label.name or "").strip().casefold()
        if actual != expected:
            matched = False

    existing = db.execute(
        select(CallLabelResult).where(
            CallLabelResult.call_id == call_id,
            CallLabelResult.rule_id == rule.id,
            CallLabelResult.label_id == label_id,
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing:
        existing.matched = matched
        existing.value_number = value_number  # type: ignore[assignment]
        existing.value_text = value_text
        existing.comment_text = comment_text
        existing.comment_title_snapshot = comment_title_snapshot
        existing.evaluated_at = now
        existing.updated_at = now
    else:
        db.add(
            CallLabelResult(
                call_id=call_id,
                rule_id=rule.id,
                label_id=label_id,
                matched=matched,
                value_number=value_number,
                value_text=value_text,
                comment_text=comment_text,
                comment_title_snapshot=comment_title_snapshot,
                evaluated_at=now,
            )
        )

    # keep legacy call_labels for backward compat (only when matched)
    if matched and label:
        _upsert_legacy_label(
            db, call_id=call_id, rule=rule, label_value=label.name, reason=comment_text
        )


def _upsert_legacy_label(
    db: Session,
    *,
    call_id: str,
    rule: LabelRule,
    label_value: str,
    reason: str | None,
) -> None:
    existing = db.execute(
        select(CallLabel).where(
            CallLabel.call_id == call_id,
            CallLabel.rule_id == rule.id,
        )
    ).scalar_one_or_none()
    if existing:
        existing.label_value = label_value
        existing.reason = reason
    else:
        db.add(
            CallLabel(call_id=call_id, rule_id=rule.id, label_value=label_value, reason=reason)
        )


# ── keyword rules ─────────────────────────────────────────────────────────────


def apply_keyword_rules_for_call(
    db: Session,
    call_id: str,
    segments: Sequence[TranscriptSegment],
) -> list[str]:
    """Apply all enabled KEYWORD rules; write results to call_label_results."""
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        return []
    owner_company_id = str(call.owner_company_id or "").strip() or None
    scope_filter = _rule_scope_filter_for_call(owner_company_id)

    keyword_rule_ids = list(
        db.scalars(
            select(LabelRule.id).where(
                LabelRule.rule_type == LabelRuleType.KEYWORD,
            )
        ).all()
    )
    if keyword_rule_ids:
        db.query(CallLabelResult).filter(
            CallLabelResult.call_id == call_id,
            CallLabelResult.rule_id.in_(keyword_rule_ids),
        ).delete(synchronize_session=False)
        db.query(CallLabel).filter(
            CallLabel.call_id == call_id,
            CallLabel.rule_id.in_(keyword_rule_ids),
        ).delete(synchronize_session=False)
        db.flush()

    rules = db.scalars(
        select(LabelRule).where(
            LabelRule.is_enabled.is_(True),
            LabelRule.deleted_at.is_(None),
            LabelRule.rule_type == LabelRuleType.KEYWORD,
            scope_filter,
        )
    ).all()

    applied: list[str] = []
    for rule in rules:
        cfg = json.loads(rule.config_json or "{}")
        query = str(cfg.get("query") or "").strip()
        part = str(cfg.get("search_part") or "ANY")
        if not query:
            continue

        text_part = _segment_text_for_part(segments, part)
        matched = _keyword_match(query, text_part)

        label: LabelDefinition | None = None
        if rule.label_id:
            label = db.get(LabelDefinition, rule.label_id)
        if label and not _label_allowed_for_call(label, owner_company_id):
            log.warning("Keyword rule %s references foreign-company label %s, skipping", rule.id, label.id)
            continue

        _upsert_result(
            db,
            call_id=call_id,
            rule=rule,
            label=label,
            matched=matched,
            comment_text=f"keyword={query}; part={part}" if matched else None,
        )
        if matched and label:
            applied.append(label.name)

    return applied


# ── LLM rule matches ──────────────────────────────────────────────────────────


def apply_llm_rule_matches(
    db: Session,
    call_id: str,
    llm_rule_matches: list[dict],
) -> list[str]:
    """Persist LLM rule results from transcription-service into call_label_results."""
    applied: list[str] = []
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        return []
    owner_company_id = str(call.owner_company_id or "").strip() or None
    scope_filter = _rule_scope_filter_for_call(owner_company_id)
    label_scope_filter = _label_scope_filter_for_call(owner_company_id)

    def _extract_expected_text_values_from_prompt(prompt_text: str) -> list[str]:
        values: list[str] = []
        for match in re.finditer(r"\[(.*?)\]", prompt_text, flags=re.DOTALL):
            raw = match.group(1)
            parts = [p.strip() for p in re.split(r"\s*/\s*", raw) if p.strip()]
            if len(parts) >= 2 and all(len(p) <= 64 for p in parts):
                values.extend(parts)
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
        for match in re.finditer(r'["«]([^"»]{1,64})["»]\s*(?:/|или|or)\s*["«]([^"»]{1,64})["»]', prompt_text, flags=re.IGNORECASE):
            left = match.group(1).strip()
            right = match.group(2).strip()
            if left and right:
                values.extend([left, right])

        uniq: list[str] = []
        seen: set[str] = set()
        for v in values:
            key = v.casefold()
            if key not in seen:
                seen.add(key)
                uniq.append(v)
        return uniq

    def _recover_flag_value_text(prompt_text: str, matched: bool, comment: str | None, raw_value_text: str | None) -> str | None:
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

        absent_candidate = next((opt for opt in expected_values if any(marker in opt.casefold() for marker in absent_markers)), None)
        present_candidate = next((opt for opt in expected_values if any(marker in opt.casefold() for marker in present_markers)), None)

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

    # Prevent stale/duplicate rows across retries:
    # before writing fresh LLM results, clear previous LLM outputs for this call.
    llm_rule_ids = list(
        db.scalars(
            select(LabelRule.id).where(
                LabelRule.rule_type == LabelRuleType.LLM,
            )
        ).all()
    )
    if llm_rule_ids:
        db.query(CallLabelResult).filter(
            CallLabelResult.call_id == call_id,
            CallLabelResult.rule_id.in_(llm_rule_ids),
        ).delete(synchronize_session=False)
        db.query(CallLabel).filter(
            CallLabel.call_id == call_id,
            CallLabel.rule_id.in_(llm_rule_ids),
        ).delete(synchronize_session=False)
        db.flush()

    for item in llm_rule_matches:
        raw_rule_id = item.get("rule_id")
        rule_id = str(raw_rule_id or "").strip()
        if not rule_id:
            continue

        try:
            rule_id = str(UUID(rule_id))
        except ValueError:
            log.warning("LLM match has invalid rule_id=%r, skipping", raw_rule_id)
            continue

        rule = db.get(LabelRule, rule_id)
        if not rule or rule.deleted_at is not None or not rule.is_enabled:
            log.warning("LLM match references unknown rule_id=%s, skipping", rule_id)
            continue
        if owner_company_id:
            if rule.owner_company_id not in {owner_company_id, None}:
                log.warning("LLM match references foreign-company rule_id=%s, skipping", rule_id)
                continue
        elif rule.owner_company_id is not None:
            log.warning("LLM match references non-global rule_id=%s without company context, skipping", rule_id)
            continue

        matched = _coerce_matched_flag(item.get("matched", False))
        comment = str(item.get("comment") or "").strip() or None
        value_number: float | None = None
        value_text: str | None = None

        # parse value_text only (canonical contract)
        if item.get("value_text"):
            value_text = str(item["value_text"]).strip() or None

        # resolve label
        label: LabelDefinition | None = None
        kind_from_cfg = ""
        try:
            cfg = json.loads(rule.config_json or "{}")
            kind_from_cfg = str(cfg.get("kind") or "").strip().upper()
        except Exception:
            cfg = {}
            kind_from_cfg = ""
        is_comment_rule = kind_from_cfg == "COMMENT"

        if kind_from_cfg == "FLAG_VALUE":
            prompt_text = str(cfg.get("prompt") or "")
            value_text = _recover_flag_value_text(prompt_text, matched, comment, value_text)
            matched = _has_extracted_value(value_number=value_number, value_text=value_text)

        if item.get("label_id"):
            raw_label_id = str(item["label_id"]).strip()
            try:
                label = db.get(LabelDefinition, str(UUID(raw_label_id)))
                if label and not _label_allowed_for_call(label, owner_company_id):
                    label = None
            except ValueError:
                log.warning("LLM match has invalid label_id=%r for rule_id=%s", raw_label_id, rule_id)

        if label is None and matched:
            allowed = db.scalars(
                select(LabelDefinition)
                .join(LabelRuleDefinition, LabelRuleDefinition.label_id == LabelDefinition.id)
                .where(LabelRuleDefinition.rule_id == rule_id)
                .where(label_scope_filter)
            ).all()
            label_candidates: list[str] = []
            if value_text:
                label_candidates.append(value_text.strip().lower())

            for candidate in label_candidates:
                if not candidate:
                    continue
                for ld in allowed:
                    if ld.name.strip().lower() == candidate or ld.code.strip().lower() == candidate:
                        label = ld
                        break
                if label is not None:
                    break

        if label is None and rule.label_id:
            label = db.get(LabelDefinition, rule.label_id)
            if label and not _label_allowed_for_call(label, owner_company_id):
                label = None

        if kind_from_cfg == "FLAG" and matched:
            allowed = db.scalars(
                select(LabelDefinition)
                .join(LabelRuleDefinition, LabelRuleDefinition.label_id == LabelDefinition.id)
                .where(LabelRuleDefinition.rule_id == rule_id)
                .where(label_scope_filter)
            ).all()
            allowed_names = {ld.name.strip().casefold() for ld in allowed}
            actual_value = str(value_text or "").strip().casefold()
            if not actual_value or actual_value not in allowed_names:
                matched = False
                if comment is None:
                    comment = "Значение не соответствует выбранным меткам правила"

        if is_comment_rule:
            label = None

        _upsert_result(
            db,
            call_id=call_id,
            rule=rule,
            label=label,
            matched=matched,
            value_number=value_number,
            value_text=value_text,
            comment_text=comment,
        )
        if matched and is_comment_rule:
            applied.append(rule.name)
        elif matched and label:
            applied.append(label.name)

    return applied
