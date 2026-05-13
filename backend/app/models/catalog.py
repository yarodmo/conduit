"""
Conduit Backend — Material Catalog Models (M12)
Suppliers + Import Jobs. MaterialCatalog extended fields live in takeoff.py.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ConduitBase

# MEP category tree
MEP_CATEGORIES = [
    "HVAC", "Plumbing", "Electrical", "Controls",
    "Fire Protection", "Medical Gas", "Low Voltage", "Structural Support",
]


class CatalogSupplier(ConduitBase):
    __tablename__ = "catalog_suppliers"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)


class CatalogImportJob(ConduitBase):
    __tablename__ = "catalog_import_jobs"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    rows_total: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    rows_created: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
