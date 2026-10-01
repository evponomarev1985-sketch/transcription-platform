"""Add label_definitions, label_rule_definitions, call_label_results; extend label_rules

Revision ID: 20260924_0002
Revises: 20260922_0001
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260924_0002"
down_revision = "20260922_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── enums ──────────────────────────────────────────────────────────────────
    label_kind = sa.Enum("FLAG", "FLAG_VALUE", "COMMENT", name="label_kind")
    label_value_type = sa.Enum("NUMBER", "TEXT", name="label_value_type")
    label_kind.create(op.get_bind(), checkfirst=True)
    label_value_type.create(op.get_bind(), checkfirst=True)

    # ── label_definitions ─────────────────────────────────────────────────────
    op.create_table(
        "label_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", label_kind, nullable=False),
        sa.Column("value_type", label_value_type, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_label_definitions_code"),
    )

    # ── label_rule_definitions (join: rule ↔ allowed labels) ─────────────────
    op.create_table(
        "label_rule_definitions",
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("label_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "label_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("label_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("rule_id", "label_id", name="pk_label_rule_definitions"),
    )
    op.create_index("ix_lrd_rule_id", "label_rule_definitions", ["rule_id"])
    op.create_index("ix_lrd_label_id", "label_rule_definitions", ["label_id"])

    # ── call_label_results ────────────────────────────────────────────────────
    op.create_table(
        "call_label_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("label_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "label_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("label_definitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("matched", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("value_number", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("comment_text", sa.Text(), nullable=True),
        sa.Column("comment_title_snapshot", sa.Text(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("call_id", "rule_id", "label_id", name="uq_call_rule_label_result"),
    )
    op.create_index("ix_clr_call_id", "call_label_results", ["call_id"])
    op.create_index("ix_clr_rule_id", "call_label_results", ["rule_id"])
    op.create_index("ix_clr_label_id", "call_label_results", ["label_id"])

    # ── extend label_rules: add label_id FK ───────────────────────────────────
    op.add_column(
        "label_rules",
        sa.Column(
            "label_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("label_definitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_label_rules_label_id", "label_rules", ["label_id"])


def downgrade() -> None:
    op.drop_index("ix_label_rules_label_id", table_name="label_rules")
    op.drop_column("label_rules", "label_id")

    op.drop_index("ix_clr_label_id", table_name="call_label_results")
    op.drop_index("ix_clr_rule_id", table_name="call_label_results")
    op.drop_index("ix_clr_call_id", table_name="call_label_results")
    op.drop_table("call_label_results")

    op.drop_index("ix_lrd_label_id", table_name="label_rule_definitions")
    op.drop_index("ix_lrd_rule_id", table_name="label_rule_definitions")
    op.drop_table("label_rule_definitions")

    op.drop_table("label_definitions")

    label_value_type = sa.Enum("NUMBER", "TEXT", name="label_value_type")
    label_kind = sa.Enum("FLAG", "FLAG_VALUE", "COMMENT", name="label_kind")
    label_value_type.drop(op.get_bind(), checkfirst=True)
    label_kind.drop(op.get_bind(), checkfirst=True)
