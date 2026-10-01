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
    op.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS owner_company_id UUID")
    op.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS owner_company_name VARCHAR(255)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_calls_owner_company_id ON calls (owner_company_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_calls_owner_company_id")
    op.execute("ALTER TABLE calls DROP COLUMN IF EXISTS owner_company_name")
    op.execute("ALTER TABLE calls DROP COLUMN IF EXISTS owner_company_id")
