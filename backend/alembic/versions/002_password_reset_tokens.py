"""Sprint 1.1 — Forensic fix: Password reset tokens (GAP-001)

Revision ID: 002_password_reset_tokens
Revises: 001_initial_schema
Create Date: 2026-04-28 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "002_password_reset_tokens"
down_revision: str | None = "001_initial_schema"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Password Reset Tokens ──
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_password_reset_user", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_email", "password_reset_tokens", ["email"])


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
