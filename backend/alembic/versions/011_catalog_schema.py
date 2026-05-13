"""011_catalog_schema — Material Catalog extensions: tag_prefix, category,
embedding, suppliers, import jobs (M12)

Revision ID: 011_catalog_schema
Revises: 010_collaboration_schema
Create Date: 2026-05-13

Bliss Systems LLC — APEX Standard
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "011_catalog_schema"
down_revision: str | None = "010_collaboration_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extend material_catalog ────────────────────────────────────────
    op.add_column("material_catalog",
                  sa.Column("tag_prefix", sa.String(50), nullable=True))
    op.add_column("material_catalog",
                  sa.Column("category", sa.String(50), nullable=True))
    op.add_column("material_catalog",
                  sa.Column("description", sa.Text(), nullable=True))
    op.add_column("material_catalog",
                  sa.Column("is_custom", sa.Boolean(), nullable=False,
                             server_default="false"))
    op.add_column("material_catalog",
                  sa.Column("supplier_sku", sa.String(255), nullable=True))
    # embedding stored as JSON array of floats; production can cast to vector
    op.add_column("material_catalog",
                  sa.Column("embedding", sa.JSON(), nullable=True))

    op.create_index("ix_material_catalog_org_category",
                    "material_catalog", ["org_id", "category"])
    op.create_index("ix_material_catalog_tag_prefix",
                    "material_catalog", ["tag_prefix"])

    # ── catalog_suppliers ──────────────────────────────────────────────
    op.create_table(
        "catalog_suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("website", sa.String(512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "name", name="uq_supplier_org_name"),
    )
    op.create_index("ix_catalog_suppliers_org_id", "catalog_suppliers", ["org_id"])

    # ── catalog_import_jobs ────────────────────────────────────────────
    op.create_table(
        "catalog_import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'queued'"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=True),
        sa.Column("rows_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_catalog_import_jobs_org_id", "catalog_import_jobs", ["org_id"])


def downgrade() -> None:
    op.drop_table("catalog_import_jobs")
    op.drop_table("catalog_suppliers")
    op.drop_index("ix_material_catalog_tag_prefix", "material_catalog")
    op.drop_index("ix_material_catalog_org_category", "material_catalog")
    for col in ("embedding", "supplier_sku", "is_custom",
                "description", "category", "tag_prefix"):
        op.drop_column("material_catalog", col)
