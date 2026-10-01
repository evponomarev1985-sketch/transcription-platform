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
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            normalized_name VARCHAR(255) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_normalized_name ON companies (normalized_name)")

    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(128)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(128)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS company_id UUID")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS marketing_consent BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_accepted_at TIMESTAMPTZ")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_company_id ON users (company_id)")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_company_id') THEN
                ALTER TABLE users
                ADD CONSTRAINT fk_users_company_id FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL;
            END IF;
        END
        $$;
        """
    )

    op.execute("""
    UPDATE users
    SET first_name = COALESCE(first_name, ''),
        last_name = COALESCE(last_name, '')
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_company_id")
    op.execute("DROP INDEX IF EXISTS ix_users_company_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS privacy_accepted_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS terms_accepted_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS marketing_consent")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS company_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_name")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS first_name")

    op.execute("DROP INDEX IF EXISTS ix_companies_normalized_name")
    op.execute("DROP TABLE IF EXISTS companies")
