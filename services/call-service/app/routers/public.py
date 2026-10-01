from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from botocore.exceptions import ClientError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..checklists import evaluate_checklists_for_call
from ..db import get_db
from ..models import Call, CallLabelResult, CallStatus, JobStatus, LabelKind, Transcript, TranscriptSegment, TranscriptionJob
from ..queue import publish_message
from ..schemas import (
    CallCommentOut,
    CallLabelResultOut,
    CallListOut,
    CallOut,
    RetryResult,
    SegmentOut,
    TranscriptOut,
    UpdateSegmentRequest,
)
from ..security import parse_access_token
from ..storage import create_presigned_get_url, get_object

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])

LOW_CONFIDENCE_MARKERS = {
    "не уверен",
    "не увер",
    "возможно",
    "вероятно",
    "предполож",
    "кажется",
    "неясно",
    "не ясно",
    "непонят",
    "сомне",
    "может быть",
    "по всей видимости",
}


def _is_admin(payload: dict) -> bool:
    return str(payload.get("role")) == "ADMIN"


def _result_kind(r: CallLabelResult) -> LabelKind | None:
    if r.label:
        return r.label.kind
    if not r.rule:
        return None
    try:
        cfg = json.loads(r.rule.config_json or "{}")
    except Exception:
        return None
    kind = str(cfg.get("kind") or "").upper()
    if kind in {"FLAG", "FLAG_VALUE", "COMMENT"}:
        return LabelKind(kind)
    return None


def _review_flags_for_result(r: CallLabelResult) -> list[str]:
    reasons: list[str] = []
    comment = (r.comment_text or "").strip().lower()
    result_kind = _result_kind(r)

    if r.matched and result_kind == LabelKind.FLAG_VALUE:
        has_numeric_value = r.value_number is not None
        has_text_value = bool((r.value_text or "").strip())
        if not has_numeric_value and not has_text_value:
            reasons.append("FLAG_VALUE without extracted value")

    if result_kind == LabelKind.FLAG and r.matched and r.label:
        if not (r.value_text or "").strip():
            reasons.append("FLAG matched without value_text")
        elif (r.value_text or "").strip().casefold() != (r.label.name or "").strip().casefold():
            reasons.append("FLAG value_text does not match selected label")

    if r.matched and not comment:
        reasons.append("Matched result without explanation comment")

    if comment:
        for marker in LOW_CONFIDENCE_MARKERS:
            if marker in comment:
                reasons.append(f"Low-confidence marker in comment: {marker}")
                break

    if result_kind == LabelKind.FLAG_VALUE and (r.value_text or "").strip() and comment:
        if "не выяв" in comment and "не выяв" not in (r.value_text or "").strip().lower():
            reasons.append("Comment says 'not identified' but value_text is concrete")

    return reasons


def _label_result_out(r: CallLabelResult) -> CallLabelResultOut:
    review_reasons = _review_flags_for_result(r)
    result_kind = _result_kind(r)
    return CallLabelResultOut(
        id=r.id,
        rule_id=r.rule_id,
        rule_name=r.rule.name if r.rule else None,
        label_id=r.label_id,
        label_code=r.label.code if r.label else None,
        label_name=r.label.name if r.label else None,
        label_kind=result_kind.value if result_kind else None,  # type: ignore[arg-type]
        matched=r.matched,
        value_number=float(r.value_number) if r.value_number is not None else None,
        value_text=r.value_text,
        comment_text=r.comment_text,
        comment_title_snapshot=r.comment_title_snapshot,
        needs_review=bool(review_reasons),
        review_reasons=review_reasons,
        evaluated_at=r.evaluated_at,
    )


def _call_out(call: Call) -> CallOut:
    all_results = [_label_result_out(r) for r in (call.label_results or [])]
    matched_results = [r for r in all_results if r.matched]
    matched_label_results = [r for r in matched_results if r.label_kind != "COMMENT"]
    unmatched_results = [r for r in all_results if not r.matched]
    needs_review_results = [r for r in matched_label_results if r.needs_review]
    # backward-compat flat labels (deduplicated by label name)
    label_names: list[str] = []
    seen_names: set[str] = set()
    for r in matched_label_results:
        name = r.label_name or ""
        if name and name not in seen_names:
            seen_names.add(name)
            label_names.append(name)
    # fallback to legacy call_labels if no new results
    if not label_names:
        for lbl in (call.labels or []):
            if lbl.label_value and lbl.label_value not in seen_names:
                seen_names.add(lbl.label_value)
                label_names.append(lbl.label_value)

    checklists = call._checklists_for_evaluation if hasattr(call, "_checklists_for_evaluation") else []
    checklist_results = evaluate_checklists_for_call(
        call_id=call.id,
        checklists=checklists,
        call_results=(call.label_results or []),
    )

    return CallOut(
        id=call.id,
        title=call.title,
        source_file_name=call.source_file_name,
        owner_user_id=call.owner_user_id,
        owner_login=call.owner_login,
        language=call.language,
        duration_seconds=call.duration_seconds,
        status=call.status.value,  # type: ignore[arg-type]
        progress=call.progress,
        error_message=call.error_message,
        uploaded_at=call.uploaded_at,
        label_results=matched_label_results,
        label_results_unmatched=unmatched_results,
        label_results_needs_review=needs_review_results,
        labels=sorted(label_names),
        checklist_results=checklist_results,
    )


def _normalize_speaker_token(label: str | None) -> str:
    return str(label).strip().upper() if label is not None else ""


def _infer_transcript_meta(
    labels: set[str],
    source_file_name: str,
) -> tuple[Literal["v2", "v3", "unknown"], Literal["on", "off", "unknown"]]:
    if not labels:
        return "unknown", "off"

    has_zero = any(token in {"0", "CH0", "CHANNEL_0"} for token in labels)
    has_named = any(token.startswith("SPEAKER_") for token in labels)
    has_numeric = any(token in {"1", "2", "CH1", "CH2", "CHANNEL_1", "CHANNEL_2"} for token in labels)

    stt_version: Literal["v2", "v3", "unknown"]
    if has_zero or has_named:
        stt_version = "v3"
    elif has_numeric:
        stt_version = "v2"
    else:
        stt_version = "unknown"

    ext = source_file_name.lower().rsplit(".", 1)
    is_mp3 = len(ext) > 1 and ext[-1] == "mp3"

    if is_mp3 and stt_version == "v3":
        # In our pipeline for v3 we disable speakerLabeling for MP3 to avoid
        # SpeechKit mono-only limitation errors; labels still can differ by channel.
        speaker_labeling: Literal["on", "off", "unknown"] = "off"
    else:
        speaker_labeling = "on" if len(labels) >= 2 else "off"
    return stt_version, speaker_labeling


@router.get("", response_model=CallListOut)
def list_calls(
    authorization: str | None = Header(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    owner_login: str | None = None,
    sort_by: str = "uploaded_at",
    sort_order: str = "desc",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> CallListOut:
    payload = parse_access_token(authorization)
    filters: list[Any] = [Call.deleted_at.is_(None)]

    if not _is_admin(payload):
        filters.append(Call.owner_user_id == str(payload["sub"]))
    elif owner_login:
        filters.append(func.lower(Call.owner_login) == owner_login.lower())

    if search:
        like = f"%{search}%"
        filters.append(or_(Call.title.ilike(like), Call.source_file_name.ilike(like)))

    if status_filter:
        try:
            parsed = CallStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
        filters.append(Call.status == parsed)

    if date_from:
        filters.append(Call.uploaded_at >= date_from)
    if date_to:
        filters.append(Call.uploaded_at <= date_to)

    total = db.scalar(select(func.count(Call.id)).where(and_(*filters))) or 0

    sort_column = {
        "uploaded_at": Call.uploaded_at,
        "title": Call.title,
        "status": Call.status,
        "progress": Call.progress,
    }.get(sort_by, Call.uploaded_at)
    order_expr = sort_column.desc() if sort_order.lower() == "desc" else sort_column.asc()

    rows = db.scalars(
        select(Call)
        .where(and_(*filters))
        .options(
            selectinload(Call.labels),
            selectinload(Call.label_results).selectinload(CallLabelResult.label),
            selectinload(Call.label_results).selectinload(CallLabelResult.rule),
        )
        .order_by(order_expr)
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    from ..models import Checklist

    active_checklists = db.scalars(
        select(Checklist).where(Checklist.is_active.is_(True)).order_by(Checklist.created_at.asc())
    ).all()
    for call in rows:
        setattr(call, "_checklists_for_evaluation", active_checklists)

    return CallListOut(items=[_call_out(c) for c in rows], page=page, size=size, total=int(total))


@router.get("/{call_id}", response_model=CallOut)
def get_call(call_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> CallOut:
    payload = parse_access_token(authorization)
    call = db.execute(
        select(Call)
        .where(Call.id == call_id)
        .options(
            selectinload(Call.labels),
            selectinload(Call.label_results).selectinload(CallLabelResult.label),
            selectinload(Call.label_results).selectinload(CallLabelResult.rule),
        )
    ).scalar_one_or_none()
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if not _is_admin(payload) and call.owner_user_id != str(payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    from ..models import Checklist

    active_checklists = db.scalars(
        select(Checklist).where(Checklist.is_active.is_(True)).order_by(Checklist.created_at.asc())
    ).all()
    setattr(call, "_checklists_for_evaluation", active_checklists)
    return _call_out(call)


@router.get("/{call_id}/comments", response_model=list[CallCommentOut])
def get_call_comments(
    call_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> list[CallCommentOut]:
    """Return all comment entries for a call (right column in UI)."""
    payload = parse_access_token(authorization)
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if not _is_admin(payload) and call.owner_user_id != str(payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    results = db.scalars(
        select(CallLabelResult)
        .where(
            CallLabelResult.call_id == call_id,
            CallLabelResult.matched.is_(True),
        )
        .options(
            selectinload(CallLabelResult.label),
            selectinload(CallLabelResult.rule),
        )
        .order_by(CallLabelResult.evaluated_at.asc())
    ).all()

    comments: list[CallCommentOut] = []
    for r in results:
        kind_enum = _result_kind(r)
        kind = kind_enum.value if kind_enum else None
        comment_body = r.comment_text or ""
        if not comment_body:
            continue  # skip results with no comment

        value_display: str | None = None
        if kind == "COMMENT":
            title = r.comment_title_snapshot or (r.rule.name if r.rule else "Комментарий")
            body = comment_body
        elif kind == "FLAG_VALUE":
            title = r.label.name if r.label else "Метка"
            body = comment_body
            if r.value_number is not None:
                n = float(r.value_number)
                value_display = str(int(n) if n == int(n) else n)
            elif r.value_text:
                value_display = r.value_text
        else:  # FLAG
            title = r.label.name if r.label else "Метка"
            body = comment_body

        comments.append(
            CallCommentOut(
                result_id=r.id,
                rule_id=r.rule_id,
                label_id=r.label_id,
                title=title,
                body=body,
                label_kind=kind,  # type: ignore[arg-type]
                value_display=value_display,
                evaluated_at=r.evaluated_at,
            )
        )
    return comments


@router.delete("/{call_id}")
def delete_call(call_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, str]:
    payload = parse_access_token(authorization)
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if not _is_admin(payload) and call.owner_user_id != str(payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    call.deleted_at = datetime.now(UTC)
    db.commit()
    return {"status": "ok"}


@router.post("/{call_id}/retry", response_model=RetryResult)
def retry_call(call_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> RetryResult:
    payload = parse_access_token(authorization)
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if not _is_admin(payload) and call.owner_user_id != str(payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    job = db.execute(select(TranscriptionJob).where(TranscriptionJob.call_id == call.id)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job.status = JobStatus.QUEUED
    job.last_error = None
    job.operation_id = None
    job.attempt += 1
    job.version += 1

    call.status = CallStatus.QUEUED
    call.progress = 0
    call.error_message = None

    db.commit()

    publish_message(
        {
            "schema_version": 1,
            "message_id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "job_id": job.id,
            "call_id": call.id,
            "action": "SUBMIT",
            "attempt": job.attempt,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    return RetryResult(job_id=job.id, status=job.status.value)


@router.get("/{call_id}/audio")
def stream_audio(
    call_id: str,
    authorization: str | None = Header(default=None),
    range_header: str | None = Header(default=None, alias="Range"),
    db: Session = Depends(get_db),
) -> Response:
    payload = parse_access_token(authorization)
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if not _is_admin(payload) and call.owner_user_id != str(payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    ext = call.source_file_name.lower().rsplit(".", 1)
    mime_by_ext = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "opus": "audio/ogg",
    }
    mime_type = mime_by_ext.get(ext[-1], "application/octet-stream") if len(ext) > 1 else "application/octet-stream"

    try:
        obj = get_object(call.object_key, range_header)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "404"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio object not found") from exc
        if code in {"InvalidRange", "416"}:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range") from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to read audio object") from exc

    body = obj["Body"].read()
    response_headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=300",
        "Content-Type": mime_type,
    }

    content_range = obj.get("ContentRange")
    if content_range:
        response_headers["Content-Range"] = str(content_range)
        response_headers["Content-Length"] = str(obj.get("ContentLength", len(body)))
        return Response(content=body, status_code=status.HTTP_206_PARTIAL_CONTENT, headers=response_headers)

    response_headers["Content-Length"] = str(obj.get("ContentLength", len(body)))
    return Response(content=body, status_code=status.HTTP_200_OK, headers=response_headers)


@router.get("/{call_id}/audio-url")
def get_audio_url(call_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, str]:
    payload = parse_access_token(authorization)
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if not _is_admin(payload) and call.owner_user_id != str(payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return {"url": create_presigned_get_url(call.object_key)}


@router.get("/{call_id}/transcript", response_model=TranscriptOut)
def get_transcript(call_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> TranscriptOut:
    payload = parse_access_token(authorization)
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if not _is_admin(payload) and call.owner_user_id != str(payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    transcript = (
        db.execute(select(Transcript).where(Transcript.call_id == call.id).options(joinedload(Transcript.segments)))
        .unique()
        .scalar_one_or_none()
    )
    if not transcript:
        return TranscriptOut(call_id=call.id, full_text="", language=call.language, stt_version="unknown", speaker_labeling="unknown", segments=[])
    ordered = sorted(transcript.segments, key=lambda x: x.segment_order)
    labels = {_normalize_speaker_token(item.speaker_label) for item in ordered if _normalize_speaker_token(item.speaker_label)}
    stt_version, speaker_labeling = _infer_transcript_meta(labels, call.source_file_name)
    return TranscriptOut(
        call_id=call.id,
        full_text=transcript.full_text,
        language=transcript.language,
        stt_version=stt_version,
        speaker_labeling=speaker_labeling,
        segments=[
            SegmentOut(
                id=item.id,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                text=item.text,
                speaker_label=item.speaker_label,
                confidence=float(item.confidence) if item.confidence is not None else None,
                segment_order=item.segment_order,
            )
            for item in ordered
        ],
    )


@router.patch("/{call_id}/segments/{segment_id}")
def update_segment(
    call_id: str,
    segment_id: str,
    payload: UpdateSegmentRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user_payload = parse_access_token(authorization)
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if not _is_admin(user_payload) and call.owner_user_id != str(user_payload["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    segment = db.get(TranscriptSegment, segment_id)
    if not segment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")
    segment.text = payload.text

    transcript = db.get(Transcript, segment.transcript_id)
    if transcript:
        items = db.scalars(
            select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id).order_by(TranscriptSegment.segment_order.asc())
        ).all()
        transcript.full_text = " ".join(x.text for x in items)

    db.commit()
    return {"status": "ok"}
