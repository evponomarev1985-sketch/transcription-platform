from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from .models import CallLabelResult, LabelKind
from .schemas import CallChecklistResultOut, ChecklistQuestionResultOut


def _value_matches(result: CallLabelResult, expected_value: str | None) -> bool:
    if expected_value is None:
        return True
    expected = expected_value.strip().casefold()
    if not expected:
        return True

    if result.label and result.label.kind == LabelKind.FLAG:
        label_name = (result.label.name or "").strip().casefold()
        return label_name == expected

    actual_candidates: list[str] = []
    if result.label and result.label.name:
        actual_candidates.append(str(result.label.name).strip().casefold())
    if result.value_text is not None:
        actual_candidates.append(str(result.value_text).strip().casefold())
    if result.value_number is not None:
        n = float(result.value_number)
        actual_candidates.append((str(int(n)) if n == int(n) else str(n)).casefold())
    return expected in actual_candidates


def _target_matches(result: CallLabelResult, target: dict) -> bool:
    values = target.get("values") or []
    if values:
        return any(_value_matches(result, str(v)) for v in values)
    return _value_matches(result, target.get("value"))


def _line_matches(line: dict, matched_results: list[CallLabelResult]) -> bool:
    operator = str(line.get("operator") or "").upper()
    raw_targets = line.get("targets") or []
    targets: list[dict] = [x for x in raw_targets if isinstance(x, dict) and x.get("label_id")]
    if not targets:
        return False

    per_target: list[bool] = []
    for target in targets:
        target_label_id = str(target.get("label_id") or "").strip()
        exists = any(
            (r.label_id == target_label_id and _target_matches(r, target))
            for r in matched_results
        )
        per_target.append(exists)

    if operator == "INCLUDE_ANY":
        return any(per_target)
    if operator == "INCLUDE_ALL":
        return all(per_target)
    if operator == "EXCLUDE_ANY":
        return not any(per_target)
    if operator == "EXCLUDE_ALL":
        return not all(per_target)
    return False


def _all_lines_match(lines: list[dict], matched_results: list[CallLabelResult]) -> bool:
    if not lines:
        return True
    return all(_line_matches(line, matched_results) for line in lines)


def evaluate_checklists_for_call(
    call_id: str,
    checklists: list[object],
    call_results: list[CallLabelResult],
) -> list[CallChecklistResultOut]:
    matched_results = [r for r in call_results if r.matched]
    now = datetime.now(UTC)
    output: list[CallChecklistResultOut] = []

    for checklist in checklists:
        cfg = json.loads(getattr(checklist, "config_json", "{}") or "{}")
        filters = cfg.get("apply_filters") or []
        questions = cfg.get("questions") or []

        applicable = _all_lines_match(filters, matched_results)
        question_results: list[ChecklistQuestionResultOut] = []
        total_score = 0.0
        max_score = 0.0

        for q in questions:
            qid = str(q.get("id") or uuid4())
            q_text = str(q.get("text") or "").strip()
            answers = q.get("answers") or []
            best_answer = None
            best_score = -1.0
            q_max = 0.0
            for answer in answers:
                score = float(answer.get("score") or 0.0)
                if score > q_max:
                    q_max = score
                if _all_lines_match(answer.get("conditions") or [], matched_results):
                    if score > best_score:
                        best_score = score
                        best_answer = answer

            selected_score = float(best_answer.get("score") or 0.0) if best_answer else 0.0
            passed = best_answer is not None
            if applicable:
                total_score += selected_score
                max_score += q_max

            question_results.append(
                ChecklistQuestionResultOut(
                    question_id=qid,
                    question_text=q_text,
                    answer_text=(str(best_answer.get("text") or "") if best_answer else None),
                    score=selected_score if applicable else 0.0,
                    max_score=q_max if applicable else q_max,
                    passed=passed if applicable else False,
                )
            )

        completion = 0.0
        if applicable and max_score > 0:
            completion = round((total_score / max_score) * 100.0, 2)

        output.append(
            CallChecklistResultOut(
                checklist_id=getattr(checklist, "id"),
                checklist_name=getattr(checklist, "name"),
                is_applicable=applicable,
                total_score=round(total_score, 2) if applicable else 0.0,
                max_score=round(max_score, 2) if applicable else 0.0,
                completion_percent=completion,
                evaluated_at=now,
                questions=question_results,
            )
        )

    return output
