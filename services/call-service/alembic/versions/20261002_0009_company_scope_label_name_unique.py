"""enforce label name uniqueness per company

Revision ID: 20261002_0009
Revises: 20261002_0008
Create Date: 2026-10-02
"""

from alembic import op


revision = "20261002_0009"
down_revision = "20261002_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_label_definitions_name_company "
        "ON label_definitions (name, owner_company_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_label_definitions_name_company")
