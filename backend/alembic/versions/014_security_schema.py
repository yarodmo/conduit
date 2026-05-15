"""014_security_schema — Security Events runtime monitoring (M14)

Revision ID: 014_security_schema
Revises: 013_learning_schema
Create Date: 2026-05-15

Bliss Systems LLC — APEX Standard
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "014_security_schema"
down_revision: str | None = "013_learning_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_security_events_severity", "security_events",
                    ["severity", "created_at"])
    op.create_index("ix_security_events_org", "security_events",
                    ["org_id", "created_at"])
    op.create_index("ix_security_events_type", "security_events",
                    ["event_type", "created_at"])
    op.create_index("ix_security_events_ip", "security_events", ["ip_address"])


def downgrade() -> None:
    op.drop_table("security_events")
