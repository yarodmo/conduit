"""Sprint 2 — Fix schema drift: rename is_verified → is_superadmin in users table.

Revision ID: 003_user_superadmin_field
Revises: 002_password_reset_tokens
Create Date: 2026-05-09 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "003_user_superadmin_field"
down_revision: str | None = "002_password_reset_tokens"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "is_verified",
        new_column_name="is_superadmin",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default="false",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "is_superadmin",
        new_column_name="is_verified",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default="false",
    )
