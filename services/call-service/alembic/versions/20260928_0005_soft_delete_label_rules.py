"""add deleted_at to label_rules and soft-delete existing orphans

Revision ID: 20260928_0005
Revises: 20260925_0004
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0005"
down_revision = "20260925_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("label_rules", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("label_rules", "deleted_at")
