"""007_field_schema — Work Zones, Progress Reports, Field Photos (M6)

Revision ID: 007
Revises: 006
Create Date: 2026-05-12

Bliss Systems LLC — APEX Standard
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007_field_schema"
down_revision: str | None = "006_rfi_schema"
branch_labels = None
depends_on = None

ZONE_STATUS = postgresql.ENUM(
    "NOT_STARTED", "IN_PROGRESS", "COMPLETED", "BLOCKED",
    name="zone_status_enum",
)


def upgrade() -> None:
    ZONE_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "work_zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("systems", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="NOT_STARTED"),
        sa.Column("geofence", sa.JSON(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("blocked_rfi_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rfis.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_work_zones_project_id", "work_zones", ["project_id"])
    op.create_index("ix_work_zones_org_id", "work_zones", ["org_id"])
    op.create_index("ix_work_zones_status", "work_zones", ["status"])

    op.create_table(
        "zone_progress_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("work_zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reported_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("materials_used", sa.JSON(), nullable=True),
        sa.Column("gps_lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("gps_lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_zone_reports_zone_id", "zone_progress_reports", ["zone_id"])

    op.create_table(
        "field_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("zone_progress_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_field_photos_report_id", "field_photos", ["report_id"])


def downgrade() -> None:
    op.drop_table("field_photos")
    op.drop_table("zone_progress_reports")
    op.drop_table("work_zones")
    ZONE_STATUS.drop(op.get_bind(), checkfirst=True)
