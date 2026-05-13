"""009_reports_schema — Report Jobs async queue (M9)

Revision ID: 009_reports_schema
Revises: 008_notifications_schema
Create Date: 2026-05-13

Bliss Systems LLC — APEX Standard
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009_reports_schema"
down_revision: str | None = "008_notifications_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("report_type", sa.String(40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'queued'"),
        sa.Column("s3_key", sa.String(1024), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_report_jobs_org_id", "report_jobs", ["org_id"])
    op.create_index("ix_report_jobs_created_by", "report_jobs", ["created_by"])
    op.create_index("ix_report_jobs_status", "report_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("report_jobs")
