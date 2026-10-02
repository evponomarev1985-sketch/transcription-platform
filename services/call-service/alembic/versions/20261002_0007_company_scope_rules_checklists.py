"""add company ownership fields for label rules and checklists

Revision ID: 20261002_0007
Revises: 20261001_0006
Create Date: 2026-10-02
"""

from alembic import op


revision = "20261002_0007"
down_revision = "20261001_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE label_rules ADD COLUMN IF NOT EXISTS owner_company_id UUID")
    op.execute("ALTER TABLE label_rules ADD COLUMN IF NOT EXISTS owner_company_name VARCHAR(255)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_label_rules_owner_company_id ON label_rules (owner_company_id)")

    op.execute("ALTER TABLE checklists ADD COLUMN IF NOT EXISTS owner_company_id UUID")
    op.execute("ALTER TABLE checklists ADD COLUMN IF NOT EXISTS owner_company_name VARCHAR(255)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_checklists_owner_company_id ON checklists (owner_company_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_label_rules_owner_company_id")
    op.execute("ALTER TABLE label_rules DROP COLUMN IF EXISTS owner_company_name")
    op.execute("ALTER TABLE label_rules DROP COLUMN IF EXISTS owner_company_id")

    op.execute("DROP INDEX IF EXISTS ix_checklists_owner_company_id")
    op.execute("ALTER TABLE checklists DROP COLUMN IF EXISTS owner_company_name")
    op.execute("ALTER TABLE checklists DROP COLUMN IF EXISTS owner_company_id")
