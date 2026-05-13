"""010_collaboration_schema — Collaboration Sessions & Participants (M11)

Revision ID: 010_collaboration_schema
Revises: 009_reports_schema
Create Date: 2026-05-13

Bliss Systems LLC — APEX Standard
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010_collaboration_schema"
down_revision: str | None = "009_reports_schema"
branch_labels = None
depends_on = None

PARTICIPANT_COLORS = [
    "#E53935", "#1E88E5", "#43A047", "#FB8C00",
    "#8E24AA", "#00ACC1", "#F4511E", "#3949AB",
    "#00897B", "#6D4C41",
]


def upgrade() -> None:
    op.create_table(
        "collaboration_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("host_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_code", sa.String(10), nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="'active'"),
        sa.Column("max_participants", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_collab_sessions_plan_id", "collaboration_sessions", ["plan_id"])
    op.create_index("ix_collab_sessions_org_status",
                    "collaboration_sessions", ["org_id", "status"])
    op.create_index("ix_collab_sessions_code", "collaboration_sessions",
                    ["session_code"], unique=True)

    op.create_table(
        "session_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("collaboration_sessions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("color", sa.String(10), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.UniqueConstraint("session_id", "user_id", name="uq_session_participant"),
    )
    op.create_index("ix_session_participants_session_id",
                    "session_participants", ["session_id"])


def downgrade() -> None:
    op.drop_table("session_participants")
    op.drop_table("collaboration_sessions")
