"""Sprint 1 — Plan Processor (M3) + Plan Viewer (M4): plans, processing jobs, pages.

Revision ID: 004_plans_schema
Revises: 003_user_superadmin_field
Create Date: 2026-05-09 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_plans_schema"
down_revision: str | None = "003_user_superadmin_field"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Enums ──
    plan_source_enum = postgresql.ENUM(
        "pdf", "phone_photo", "camera_direct", "scan",
        name="plan_source_enum", create_type=True,
    )
    plan_source_enum.create(op.get_bind(), checkfirst=True)

    plan_type_enum = postgresql.ENUM(
        "hvac", "electrical", "plumbing", "mep", "fire_protection", "unknown",
        name="plan_type_enum", create_type=True,
    )
    plan_type_enum.create(op.get_bind(), checkfirst=True)

    plan_status_enum = postgresql.ENUM(
        "uploading", "queued", "processing", "ready", "failed",
        name="plan_status_enum", create_type=True,
    )
    plan_status_enum.create(op.get_bind(), checkfirst=True)

    # ── Plans ──
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("source_type", postgresql.ENUM(
            "pdf", "phone_photo", "camera_direct", "scan",
            name="plan_source_enum", create_type=False,
        ), nullable=False, server_default="pdf"),
        sa.Column("s3_key_original", sa.String(1024), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "uploading", "queued", "processing", "ready", "failed",
            name="plan_status_enum", create_type=False,
        ), nullable=False, server_default="uploading"),
        # Auto-detected metadata (STEP 3)
        sa.Column("plan_type", postgresql.ENUM(
            "hvac", "electrical", "plumbing", "mep", "fire_protection", "unknown",
            name="plan_type_enum", create_type=False,
        ), nullable=False, server_default="unknown"),
        sa.Column("scale_text", sa.String(100), nullable=True),
        sa.Column("plan_number", sa.String(100), nullable=True),
        sa.Column("plan_title", sa.String(512), nullable=True),
        sa.Column("plan_date", sa.String(50), nullable=True),
        sa.Column("plan_revision", sa.String(50), nullable=True),
        sa.Column("color_legend", postgresql.JSONB(), nullable=True),
        sa.Column("complexity_score", sa.String(20), nullable=True),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("deskew_applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plans_org_id", "plans", ["org_id"])
    op.create_index("ix_plans_project_id", "plans", ["project_id"])
    op.create_index("ix_plans_status", "plans", ["status"])

    # ── Plan Processing Jobs ──
    op.create_table(
        "plan_processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", postgresql.ENUM(
            "uploading", "queued", "processing", "ready", "failed",
            name="plan_status_enum", create_type=False,
        ), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(100), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_jobs_plan_id", "plan_processing_jobs", ["plan_id"])
    op.create_index("ix_plan_jobs_status", "plan_processing_jobs", ["status"])

    # ── Plan Pages ──
    op.create_table(
        "plan_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("s3_key_full", sa.String(1024), nullable=True),
        sa.Column("s3_key_thumb", sa.String(1024), nullable=True),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("orientation", sa.String(20), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("detected_text_blocks", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_pages_plan_id", "plan_pages", ["plan_id"])
    op.create_unique_constraint("uq_plan_pages_plan_page", "plan_pages",
                                ["plan_id", "page_number"])


def downgrade() -> None:
    op.drop_table("plan_pages")
    op.drop_table("plan_processing_jobs")
    op.drop_table("plans")
    op.execute("DROP TYPE IF EXISTS plan_status_enum")
    op.execute("DROP TYPE IF EXISTS plan_type_enum")
    op.execute("DROP TYPE IF EXISTS plan_source_enum")
