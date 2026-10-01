"""add registration/profile/company fields

Revision ID: 20261001_0002
Revises: 20260922_0001
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261001_0002"
down_revision = "20260922_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_normalized_name", "companies", ["normalized_name"], unique=True)

    op.add_column("users", sa.Column("first_name", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("company_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("users", sa.Column("marketing_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_company_id", "users", ["company_id"], unique=False)
    op.create_foreign_key("fk_users_company_id", "users", "companies", ["company_id"], ["id"], ondelete="SET NULL")

    op.execute("""
    UPDATE users
    SET first_name = COALESCE(first_name, ''),
        last_name = COALESCE(last_name, '')
    """)


def downgrade() -> None:
    op.drop_constraint("fk_users_company_id", "users", type_="foreignkey")
    op.drop_index("ix_users_company_id", table_name="users")
    op.drop_column("users", "privacy_accepted_at")
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "marketing_consent")
    op.drop_column("users", "company_id")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")

    op.drop_index("ix_companies_normalized_name", table_name="companies")
    op.drop_table("companies")
