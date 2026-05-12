"""Sprint 3 — M7 RFI & Change Orders: markups, rfis, rfi_comments, change_orders.

Revision ID: 006_rfi_schema
Revises: 005_takeoff_schema
Create Date: 2026-05-11 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_rfi_schema"
down_revision: str | None = "005_takeoff_schema"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Enums ──
    markup_type_enum = postgresql.ENUM(
        "ARROW", "RECTANGLE", "CIRCLE", "FREEHAND", "TEXT", "CLOUD", "DIMENSION",
        name="markup_type_enum", create_type=True,
    )
    markup_type_enum.create(op.get_bind(), checkfirst=True)

    rfi_status_enum = postgresql.ENUM(
        "DRAFT", "SUBMITTED", "UNDER_REVIEW", "ANSWERED", "CLOSED", "REJECTED",
        name="rfi_status_enum", create_type=True,
    )
    rfi_status_enum.create(op.get_bind(), checkfirst=True)

    rfi_urgency_enum = postgresql.ENUM(
        "LOW", "MEDIUM", "HIGH", "CRITICAL",
        name="rfi_urgency_enum", create_type=True,
    )
    rfi_urgency_enum.create(op.get_bind(), checkfirst=True)

    rfi_source_enum = postgresql.ENUM(
        "MARKUP_ESCALATED", "MANUAL", "FIELD_BLOCKED", "AI_DETECTED",
        name="rfi_source_enum", create_type=True,
    )
    rfi_source_enum.create(op.get_bind(), checkfirst=True)

    co_status_enum = postgresql.ENUM(
        "PENDING", "APPROVED", "REJECTED",
        name="co_status_enum", create_type=True,
    )
    co_status_enum.create(op.get_bind(), checkfirst=True)

    # ── Markups ──
    op.create_table(
        "markups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", postgresql.ENUM(
            "ARROW", "RECTANGLE", "CIRCLE", "FREEHAND", "TEXT", "CLOUD", "DIMENSION",
            name="markup_type_enum", create_type=False,
        ), nullable=False),
        # Coordinates relative to plan (not screen) — Anti-Kreo rule
        sa.Column("coordinates", postgresql.JSONB(), nullable=False),
        sa.Column("color", sa.String(20), nullable=False, server_default="#FF0000"),
        sa.Column("label", sa.String(512), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_markups_plan_id", "markups", ["plan_id"])
    op.create_index("ix_markups_org_id", "markups", ["org_id"])

    # ── RFIs ──
    op.create_table(
        "rfis",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("markup_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rfi_number", sa.String(30), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", postgresql.ENUM(
            "DRAFT", "SUBMITTED", "UNDER_REVIEW", "ANSWERED", "CLOSED", "REJECTED",
            name="rfi_status_enum", create_type=False,
        ), nullable=False, server_default="DRAFT"),
        sa.Column("urgency", postgresql.ENUM(
            "LOW", "MEDIUM", "HIGH", "CRITICAL",
            name="rfi_urgency_enum", create_type=False,
        ), nullable=False, server_default="MEDIUM"),
        sa.Column("source", postgresql.ENUM(
            "MARKUP_ESCALATED", "MANUAL", "FIELD_BLOCKED", "AI_DETECTED",
            name="rfi_source_enum", create_type=False,
        ), nullable=False, server_default="MANUAL"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_alerted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"]),
        sa.ForeignKeyConstraint(["markup_id"], ["markups.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "rfi_number", name="uq_rfi_number_per_project"),
    )
    op.create_index("ix_rfis_project_id", "rfis", ["project_id"])
    op.create_index("ix_rfis_org_id", "rfis", ["org_id"])
    op.create_index("ix_rfis_status", "rfis", ["status"])
    op.create_index("ix_rfis_assigned_to", "rfis", ["assigned_to"])

    # ── RFI Comments ──
    op.create_table(
        "rfi_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_official_response", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["rfi_id"], ["rfis.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rfi_comments_rfi_id", "rfi_comments", ["rfi_id"])

    # ── Change Orders ──
    op.create_table(
        "change_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("co_number", sa.String(30), nullable=False),
        sa.Column("scope_change_description", sa.Text(), nullable=False),
        sa.Column("cost_impact_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("time_impact_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("affected_systems", postgresql.JSONB(), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "PENDING", "APPROVED", "REJECTED",
            name="co_status_enum", create_type=False,
        ), nullable=False, server_default="PENDING"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_s3_key", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["rfi_id"], ["rfis.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rfi_id", name="uq_one_co_per_rfi"),
    )
    op.create_index("ix_change_orders_rfi_id", "change_orders", ["rfi_id"])
    op.create_index("ix_change_orders_org_id", "change_orders", ["org_id"])


def downgrade() -> None:
    op.drop_table("change_orders")
    op.drop_table("rfi_comments")
    op.drop_table("rfis")
    op.drop_table("markups")
    op.execute("DROP TYPE IF EXISTS co_status_enum")
    op.execute("DROP TYPE IF EXISTS rfi_source_enum")
    op.execute("DROP TYPE IF EXISTS rfi_urgency_enum")
    op.execute("DROP TYPE IF EXISTS rfi_status_enum")
    op.execute("DROP TYPE IF EXISTS markup_type_enum")
