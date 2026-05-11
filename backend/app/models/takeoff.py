"""
Conduit Backend — Takeoff Models (M5 AI Takeoff Engine)
Sprint 2: AI-powered MEP component extraction from plan images.

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON,
    Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ConduitBase


class TakeoffStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    approved = "approved"


class TakeoffJob(ConduitBase):
    __tablename__ = "takeoff_jobs"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    total_sections: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    sections_completed: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    total_items: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    low_confidence_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    accuracy_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    actual_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    total_material_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["TakeoffItem"]] = relationship(
        "TakeoffItem", back_populates="job", cascade="all, delete-orphan",
        order_by="TakeoffItem.created_at",
    )

    @property
    def is_editable(self) -> bool:
        return self.status not in ("approved",)

    @property
    def progress_pct(self) -> int:
        if self.total_sections == 0:
            return 0
        return int(self.sections_completed / self.total_sections * 100)


class TakeoffItem(ConduitBase):
    __tablename__ = "takeoff_items"

    # No deleted_at — items are hard-deleted (user explicitly removes false positives)
    takeoff_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("takeoff_jobs.id", ondelete="CASCADE"), nullable=False,
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    specification: Mapped[str] = mapped_column(String(512), nullable=False)
    system: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cfm_or_gpm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    requires_review: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    human_corrected: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    correction_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_catalog.id"), nullable=True,
    )
    unit_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    section_index: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    job: Mapped["TakeoffJob"] = relationship("TakeoffJob", back_populates="items")
    catalog_item: Mapped["MaterialCatalog | None"] = relationship("MaterialCatalog")


class MaterialCatalog(ConduitBase):
    __tablename__ = "material_catalog"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True,
    )
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)
    specification: Mapped[str] = mapped_column(String(512), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    base_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_contact: Mapped[str | None] = mapped_column(String(512), nullable=True)
    supplier_lead_days: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
