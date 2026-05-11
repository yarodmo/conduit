"""Sprint 2 — M5 AI Takeoff Engine: takeoff_jobs, takeoff_items, material_catalog.

Revision ID: 005_takeoff_schema
Revises: 004_plans_schema
Create Date: 2026-05-11 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_takeoff_schema"
down_revision: str | None = "004_plans_schema"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Enums ──
    takeoff_status_enum = postgresql.ENUM(
        "pending", "processing", "completed", "failed", "approved",
        name="takeoff_status_enum", create_type=True,
    )
    takeoff_status_enum.create(op.get_bind(), checkfirst=True)

    # ── Material Catalog ──
    op.create_table(
        "material_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),  # NULL = global
        sa.Column("item_type", sa.String(50), nullable=False),
        sa.Column("specification", sa.String(512), nullable=False),
        sa.Column("unit", sa.String(10), nullable=False),
        sa.Column("base_cost_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("supplier_name", sa.String(255), nullable=True),
        sa.Column("supplier_contact", sa.String(512), nullable=True),
        sa.Column("supplier_lead_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_material_catalog_org", "material_catalog", ["org_id"])
    op.create_index("ix_material_catalog_type", "material_catalog", ["item_type"])

    # ── Takeoff Jobs ──
    op.create_table(
        "takeoff_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", postgresql.ENUM(
            "pending", "processing", "completed", "failed", "approved",
            name="takeoff_status_enum", create_type=False,
        ), nullable=False, server_default="pending"),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=False, server_default="v1"),
        sa.Column("total_sections", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sections_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_items", sa.Integer(), nullable=True),
        sa.Column("low_confidence_count", sa.Integer(), nullable=True),
        sa.Column("accuracy_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("actual_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("total_material_cost_usd", sa.Numeric(14, 2), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_takeoff_jobs_plan_id", "takeoff_jobs", ["plan_id"])
    op.create_index("ix_takeoff_jobs_org_id", "takeoff_jobs", ["org_id"])
    op.create_index("ix_takeoff_jobs_status", "takeoff_jobs", ["status"])

    # ── Takeoff Items ──
    op.create_table(
        "takeoff_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("takeoff_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("tag", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit", sa.String(10), nullable=False),
        sa.Column("specification", sa.String(512), nullable=False),
        sa.Column("system", sa.String(30), nullable=True),
        sa.Column("cfm_or_gpm", sa.Numeric(10, 2), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("requires_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("human_corrected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("correction_notes", sa.Text(), nullable=True),
        sa.Column("catalog_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unit_cost_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(14, 2), nullable=True),
        sa.Column("section_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["takeoff_job_id"], ["takeoff_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["catalog_item_id"], ["material_catalog.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_takeoff_items_job_id", "takeoff_items", ["takeoff_job_id"])
    op.create_index("ix_takeoff_items_type", "takeoff_items", ["type"])
    op.create_index("ix_takeoff_items_review", "takeoff_items",
                    ["takeoff_job_id", "requires_review"])


def downgrade() -> None:
    op.drop_table("takeoff_items")
    op.drop_table("takeoff_jobs")
    op.drop_table("material_catalog")
    op.execute("DROP TYPE IF EXISTS takeoff_status_enum")
