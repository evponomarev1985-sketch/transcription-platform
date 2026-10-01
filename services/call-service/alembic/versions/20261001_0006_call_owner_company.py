"""add call owner company fields

Revision ID: 20261001_0006
Revises: 20260928_0005
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261001_0006"
down_revision = "20260928_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("owner_company_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("calls", sa.Column("owner_company_name", sa.String(length=255), nullable=True))
    op.create_index("ix_calls_owner_company_id", "calls", ["owner_company_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_calls_owner_company_id", table_name="calls")
    op.drop_column("calls", "owner_company_name")
    op.drop_column("calls", "owner_company_id")
