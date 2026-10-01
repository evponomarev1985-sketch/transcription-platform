from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..labeling import apply_keyword_rules_for_call, apply_llm_rule_matches
from ..models import Call, CallStatus, JobStatus, Transcript, TranscriptSegment, TranscriptionJob
from ..schemas import (
    CallCreateInternalRequest,
    JobCompleteRequest,
    JobFailRequest,
    JobOperationRegisterRequest,
    JobOut,
)
from ..security import require_internal_api_key

log = logging.getLogger("call-service.internal")

router = APIRouter(prefix="/internal/v1", tags=["internal"], dependencies=[Depends(require_internal_api_key)])


@router.post("/calls")
def create_call(payload: CallCreateInternalRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    call = Call(
        owner_user_id=payload.owner_user_id,
        owner_login=payload.owner_login,
        title=payload.title,
        source_file_name=payload.source_file_name,
        object_key=payload.object_key,
        object_bucket=payload.object_bucket,
        language=payload.language,
        status=CallStatus.QUEUED,
        progress=0,
        uploaded_at=datetime.now(UTC),
    )
    db.add(call)
    db.flush()

    job = TranscriptionJob(call_id=call.id, status=JobStatus.QUEUED, attempt=0)
    db.add(job)
    db.commit()
    return {"call_id": call.id, "job_id": job.id}


@router.get("/calls/{call_id}")
def get_call_internal(call_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    call = db.get(Call, call_id)
    if not call or call.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    return {
        "id": call.id,
        "object_key": call.object_key,
        "object_bucket": call.object_bucket,
        "source_file_name": call.source_file_name,
        "language": call.language,
    }


@router.get("/label-rules/llm-enabled")
def get_llm_rules_internal(db: Session = Depends(get_db)) -> dict[str, list[dict]]:
    from ..models import LabelDefinition, LabelRule, LabelRuleDefinition, LabelRuleType
    import json

    rules = db.scalars(
        select(LabelRule)
        .where(
            LabelRule.is_enabled.is_(True),
            LabelRule.deleted_at.is_(None),
            LabelRule.rule_type == LabelRuleType.LLM,
        )
        .order_by(LabelRule.created_at.asc())
    ).all()
    items: list[dict] = []
    for rule in rules:
        cfg = json.loads(rule.config_json or "{}")
        prompt = str(cfg.get("prompt") or "").strip()
        if not prompt:
            continue

        allowed_labels = db.scalars(
            select(LabelDefinition)
            .join(LabelRuleDefinition, LabelRuleDefinition.label_id == LabelDefinition.id)
            .where(LabelRuleDefinition.rule_id == rule.id)
            .order_by(LabelRuleDefinition.sort_order.asc())
        ).all()
        primary = allowed_labels[0] if allowed_labels else None
        kind_from_cfg = str(cfg.get("kind") or "").strip().upper()
        if kind_from_cfg in {"FLAG", "FLAG_VALUE", "COMMENT"}:
            resolved_kind = kind_from_cfg
        else:
            resolved_kind = primary.kind.value if primary else "FLAG"
        resolved_label_value = primary.name if primary else (rule.name if resolved_kind == "COMMENT" else (rule.label_value or ""))

        items.append({
            "id": rule.id,
            "name": rule.name,
            "prompt": prompt,
            "label_id": primary.id if primary else None,
            "label_value": resolved_label_value,
            "label_kind": resolved_kind,
            "allowed_labels": [
                {
                    "id": ld.id,
                    "code": ld.code,
                    "name": ld.name,
                    "kind": ld.kind.value,
                }
                for ld in allowed_labels
            ],
        })
    return {"items": items}


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(TranscriptionJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobOut(
        id=job.id,
        call_id=job.call_id,
        status=job.status.value,
        attempt=job.attempt,
        operation_id=job.operation_id,
        last_error=job.last_error,
        version=job.version,
    )


@router.post("/jobs/{job_id}/mark-processing")
def mark_processing(job_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    job = db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status == JobStatus.COMPLETED:
        return {"status": "noop"}

    call = db.get(Call, job.call_id)
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    job.status = JobStatus.PROCESSING
    job.version += 1
    call.status = CallStatus.PROCESSING
    call.progress = max(call.progress, 10)
    db.commit()
    return {"status": "ok"}


@router.post("/jobs/{job_id}/register-operation")
def register_operation(job_id: str, payload: JobOperationRegisterRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    job = db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.operation_id:
        return {"status": "noop"}
    if job.status == JobStatus.COMPLETED:
        return {"status": "noop"}
    job.operation_id = payload.operation_id
    job.status = JobStatus.PROCESSING
    job.version += 1
    db.commit()
    return {"status": "ok"}


@router.post("/jobs/{job_id}/complete")
def complete_job(job_id: str, payload: JobCompleteRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    job = db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status == JobStatus.COMPLETED:
        return {"status": "noop"}

    call = db.get(Call, job.call_id)
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    transcript = db.execute(select(Transcript).where(Transcript.call_id == call.id).with_for_update()).scalar_one_or_none()
    if not transcript:
        transcript = Transcript(call_id=call.id, full_text=payload.full_text, language=payload.language)
        db.add(transcript)
        db.flush()
    else:
        transcript.full_text = payload.full_text
        transcript.language = payload.language

    db.query(TranscriptSegment).filter(TranscriptSegment.transcript_id == transcript.id).delete()
    for seg in payload.segments:
        db.add(
            TranscriptSegment(
                transcript_id=transcript.id,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                text=seg.text,
                speaker_label=seg.speaker_label,
                confidence=seg.confidence,
                segment_order=seg.segment_order,
            )
        )

    segments = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript.id)
        .order_by(TranscriptSegment.segment_order.asc())
    ).all()

    call.status = CallStatus.COMPLETED
    call.progress = 100
    call.error_message = None
    if payload.duration_seconds is not None:
        call.duration_seconds = payload.duration_seconds

    job.status = JobStatus.COMPLETED
    job.version += 1
    job.last_error = None

    apply_keyword_rules_for_call(db, call.id, segments)
    apply_llm_rule_matches(db, call.id, [x.model_dump() for x in payload.llm_rule_matches])
    db.commit()
    log.info(
        "Job %s completed: call=%s segments=%d llm_matches=%d",
        job_id,
        call.id,
        len(payload.segments),
        len(payload.llm_rule_matches),
    )
    return {"status": "ok"}


@router.post("/jobs/{job_id}/fail")
def fail_job(job_id: str, payload: JobFailRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    job = db.execute(select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status == JobStatus.COMPLETED:
        return {"status": "noop"}

    call = db.get(Call, job.call_id)
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    job.status = JobStatus.FAILED
    job.last_error = payload.error_message
    job.version += 1
    call.status = CallStatus.FAILED
    call.error_message = payload.error_message
    call.progress = min(call.progress, 99)

    db.commit()
    return {"status": "ok"}
