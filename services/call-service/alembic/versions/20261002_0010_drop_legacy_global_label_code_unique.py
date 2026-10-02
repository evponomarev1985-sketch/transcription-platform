"""drop legacy global unique on label_definitions.code

Revision ID: 20261002_0010
Revises: 20261002_0009
Create Date: 2026-10-02
"""

from alembic import op


revision = "20261002_0010"
down_revision = "20261002_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE label_definitions DROP CONSTRAINT IF EXISTS label_definitions_code_key")
    op.execute("ALTER TABLE label_definitions DROP CONSTRAINT IF EXISTS uq_label_definitions_code")
    op.execute("DROP INDEX IF EXISTS uq_label_definitions_code")


def downgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_label_definitions_code "
        "ON label_definitions (code)"
    )
