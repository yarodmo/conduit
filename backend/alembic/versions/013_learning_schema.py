"""013_learning_schema — Self-Learning Pipeline: insights + correction events (M13)

Revision ID: 013_learning_schema
Revises: 012_assistant_schema
Create Date: 2026-05-14

Bliss Systems LLC — APEX Standard
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "013_learning_schema"
down_revision: str | None = "012_assistant_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Weekly analysis snapshots — one row per run per org
    op.create_table(
        "learning_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_takeoffs_analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_corrections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_accuracy_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("accuracy_by_version", sa.JSON(), nullable=True),   # {v1: 82.5, v2: 91.2}
        sa.Column("top_error_patterns", sa.JSON(), nullable=True),    # [{type, count, avg_conf}]
        sa.Column("low_accuracy_prompts", sa.JSON(), nullable=True),  # [v1, v2] if <70%
        sa.Column("recommendation", sa.Text(), nullable=True),        # AI-generated text
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_learning_insights_org_id", "learning_insights", ["org_id"])
    op.create_index("ix_learning_insights_period", "learning_insights",
                    ["org_id", "period_start"])

    # Per-correction audit trail
    op.create_table(
        "learning_correction_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("takeoff_job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("takeoff_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("component_type", sa.String(30), nullable=False),
        sa.Column("original_confidence", sa.Integer(), nullable=True),
        sa.Column("correction_type", sa.String(20), nullable=False),  # qty|type|spec|false_positive|missed
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_correction_events_org", "learning_correction_events",
                    ["org_id", "created_at"])
    op.create_index("ix_correction_events_prompt", "learning_correction_events",
                    ["prompt_version", "component_type"])


def downgrade() -> None:
    op.drop_table("learning_correction_events")
    op.drop_table("learning_insights")
