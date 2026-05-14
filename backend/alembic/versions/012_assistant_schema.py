"""012_assistant_schema — AI Assistant conversations, messages, offline cache (M10)

Revision ID: 012_assistant_schema
Revises: 011_catalog_schema
Create Date: 2026-05-13

Bliss Systems LLC — APEX Standard
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "012_assistant_schema"
down_revision: str | None = "011_catalog_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_asst_convs_user_org", "assistant_conversations",
                    ["user_id", "org_id"])
    op.create_index("ix_asst_convs_project", "assistant_conversations", ["project_id"])

    op.create_table(
        "assistant_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", sa.String(10), nullable=False),   # user | assistant
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_asst_messages_conv", "assistant_messages", ["conversation_id"])

    op.create_table(
        "assistant_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("context_type", sa.String(30), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "question_hash",
                            name="uq_cache_project_hash"),
    )
    op.create_index("ix_asst_cache_project", "assistant_cache",
                    ["project_id", "context_type"])


def downgrade() -> None:
    op.drop_table("assistant_cache")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
