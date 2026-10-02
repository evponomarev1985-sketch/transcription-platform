"""add company ownership fields for label definitions

Revision ID: 20261002_0008
Revises: 20261002_0007
Create Date: 2026-10-02
"""

from alembic import op


revision = "20261002_0008"
down_revision = "20261002_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE label_definitions ADD COLUMN IF NOT EXISTS owner_company_id UUID")
    op.execute("ALTER TABLE label_definitions ADD COLUMN IF NOT EXISTS owner_company_name VARCHAR(255)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_label_definitions_owner_company_id ON label_definitions (owner_company_id)"
    )
    op.execute("ALTER TABLE label_definitions DROP CONSTRAINT IF EXISTS uq_label_definitions_code")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_label_definitions_code_company "
        "ON label_definitions (code, owner_company_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_label_definitions_code_company")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_label_definitions_code "
        "ON label_definitions (code)"
    )
    op.execute("DROP INDEX IF EXISTS ix_label_definitions_owner_company_id")
    op.execute("ALTER TABLE label_definitions DROP COLUMN IF EXISTS owner_company_name")
    op.execute("ALTER TABLE label_definitions DROP COLUMN IF EXISTS owner_company_id")
