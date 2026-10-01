"""init calls schema

Revision ID: 20260922_0001
Revises: 
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260922_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    call_status = sa.Enum("UPLOADING", "QUEUED", "PROCESSING", "COMPLETED", "FAILED", name="call_status")
    job_status = sa.Enum("QUEUED", "PROCESSING", "COMPLETED", "FAILED", name="job_status")
    call_status.create(op.get_bind(), checkfirst=True)
    job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "calls",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("owner_login", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("object_bucket", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("status", call_status, nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_calls_owner_user_id", "calls", ["owner_user_id"], unique=False)
    op.create_index("ix_calls_owner_login", "calls", ["owner_login"], unique=False)
    op.create_index("ix_calls_object_key", "calls", ["object_key"], unique=True)

    op.create_table(
        "transcription_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("call_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("operation_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("call_id", name="uq_transcription_jobs_call_id"),
    )
    op.create_index("ix_transcription_jobs_operation_id", "transcription_jobs", ["operation_id"], unique=False)

    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("call_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("call_id", name="uq_transcripts_call_id"),
    )

    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("speaker_label", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("segment_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("transcript_id", "segment_order", name="uq_segment_order"),
    )
    op.create_index("ix_transcript_segments_transcript_id", "transcript_segments", ["transcript_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_transcript_segments_transcript_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")

    op.drop_table("transcripts")

    op.drop_index("ix_transcription_jobs_operation_id", table_name="transcription_jobs")
    op.drop_table("transcription_jobs")

    op.drop_index("ix_calls_object_key", table_name="calls")
    op.drop_index("ix_calls_owner_login", table_name="calls")
    op.drop_index("ix_calls_owner_user_id", table_name="calls")
    op.drop_table("calls")

    job_status = sa.Enum("QUEUED", "PROCESSING", "COMPLETED", "FAILED", name="job_status")
    call_status = sa.Enum("UPLOADING", "QUEUED", "PROCESSING", "COMPLETED", "FAILED", name="call_status")
    job_status.drop(op.get_bind(), checkfirst=True)
    call_status.drop(op.get_bind(), checkfirst=True)
