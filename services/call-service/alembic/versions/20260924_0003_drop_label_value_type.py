"""drop label_definitions.value_type

Revision ID: 20260924_0003
Revises: 20260924_0002
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0003"
down_revision = "20260924_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("label_definitions", "value_type")
    label_value_type = sa.Enum("NUMBER", "TEXT", name="label_value_type")
    label_value_type.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    label_value_type = sa.Enum("NUMBER", "TEXT", name="label_value_type")
    label_value_type.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "label_definitions",
        sa.Column("value_type", label_value_type, nullable=True),
    )
