from __future__ import annotations

import enum
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# ── enums ──────────────────────────────────────────────────────────────────────


class CallStatus(str, enum.Enum):
    UPLOADING = "UPLOADING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LabelRuleType(str, enum.Enum):
    KEYWORD = "KEYWORD"
    LLM = "LLM"


class LabelKind(str, enum.Enum):
    FLAG = "FLAG"
    FLAG_VALUE = "FLAG_VALUE"
    COMMENT = "COMMENT"


class Checklist(Base):
    __tablename__ = "checklists"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


# ── call / job / transcript ────────────────────────────────────────────────────


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    owner_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    owner_login: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    object_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, name="call_status"), default=CallStatus.QUEUED, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[TranscriptionJob | None] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    transcript: Mapped[Transcript | None] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    # legacy — kept during migration transition
    labels: Mapped[list[CallLabel]] = relationship(back_populates="call", cascade="all, delete-orphan")
    # new structured results
    label_results: Mapped[list[CallLabelResult]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    call_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.QUEUED, nullable=False
    )
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    operation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    call: Mapped[Call] = relationship(back_populates="job")


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    call_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    full_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    call: Mapped[Call] = relationship(back_populates="transcript")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="transcript", cascade="all, delete-orphan"
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("transcript_id", "segment_order", name="uq_segment_order"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    transcript_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    segment_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    transcript: Mapped[Transcript] = relationship(back_populates="segments")


# ── label_definitions (справочник меток) ──────────────────────────────────────


class LabelDefinition(Base):
    __tablename__ = "label_definitions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[LabelKind] = mapped_column(Enum(LabelKind, name="label_kind"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    rule_definitions: Mapped[list[LabelRuleDefinition]] = relationship(
        back_populates="label", cascade="all, delete-orphan"
    )
    results: Mapped[list[CallLabelResult]] = relationship(back_populates="label")


# ── label_rules ────────────────────────────────────────────────────────────────


class LabelRule(Base):
    __tablename__ = "label_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # legacy free-text — nullable going forward, kept for old rules
    label_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # FK to primary label definition
    label_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("label_definitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rule_type: Mapped[LabelRuleType] = mapped_column(
        Enum(LabelRuleType, name="label_rule_type"), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # legacy
    labels: Mapped[list[CallLabel]] = relationship(back_populates="rule")
    # new
    label_def: Mapped[LabelDefinition | None] = relationship(
        "LabelDefinition", foreign_keys=[label_id]
    )
    allowed_label_definitions: Mapped[list[LabelRuleDefinition]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        order_by="LabelRuleDefinition.sort_order",
    )
    results: Mapped[list[CallLabelResult]] = relationship(back_populates="rule")


# ── label_rule_definitions (rule ↔ allowed labels join) ───────────────────────


class LabelRuleDefinition(Base):
    """Maps which LabelDefinitions are allowed/expected for a given LabelRule.

    FLAG rules with multiple choices (e.g. Целевой/Нецелевой) have multiple rows.
    FLAG_VALUE and COMMENT rules have exactly one row.
    """

    __tablename__ = "label_rule_definitions"

    rule_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("label_rules.id", ondelete="CASCADE"),
        primary_key=True,
    )
    label_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("label_definitions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rule: Mapped[LabelRule] = relationship(back_populates="allowed_label_definitions")
    label: Mapped[LabelDefinition] = relationship(back_populates="rule_definitions")


# ── call_label_results (new structured results) ───────────────────────────────


class CallLabelResult(Base):
    __tablename__ = "call_label_results"
    __table_args__ = (
        UniqueConstraint("call_id", "rule_id", "label_id", name="uq_call_rule_label_result"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    call_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("label_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    label_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("label_definitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # for FLAG_VALUE kind
    value_number: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # comment explaining the result (required when matched=True for FLAG/FLAG_VALUE)
    comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # snapshot of rule.name at evaluation time (required for COMMENT kind)
    comment_title_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    call: Mapped[Call] = relationship(back_populates="label_results")
    rule: Mapped[LabelRule | None] = relationship(back_populates="results")
    label: Mapped[LabelDefinition | None] = relationship(back_populates="results")


# ── call_labels (legacy — kept during migration) ──────────────────────────────


class CallLabel(Base):
    __tablename__ = "call_labels"
    __table_args__ = (UniqueConstraint("call_id", "rule_id", name="uq_call_rule_label"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    call_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("label_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    label_value: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    call: Mapped[Call] = relationship(back_populates="labels")
    rule: Mapped[LabelRule | None] = relationship(back_populates="labels")
