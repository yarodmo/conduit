"""015_cached_takeoff_items — Offline AI cache on WorkZone (Sprint 7 / competitive)

Revision ID: 015_cached_takeoff_items
Revises: 014_security_schema
Create Date: 2026-05-18

Adds `cached_takeoff_items` JSON column to `work_zones`.
Populated when a takeoff is approved — Flutter reads this for offline
field access without hitting the server.

PROMPT 9 spec: "Descarga automática al asignar zona: Takeoff items de esa zona"
test_offline_takeoff_cache competitive advantage test depends on this column.

Bliss Systems LLC — APEX Standard
"""

from alembic import op
import sqlalchemy as sa

revision: str = "015_cached_takeoff_items"
down_revision: str | None = "014_security_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_zones",
        sa.Column("cached_takeoff_items", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_zones", "cached_takeoff_items")
