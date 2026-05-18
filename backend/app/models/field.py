"""
Conduit Backend — Field Coordination Models (M6)
Sprint 4: Work Zones → Progress Reports → Field Photos.

State machine enforced at service layer.

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ConduitBase


class ZoneStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


# Valid transitions — BLOCKED auto-creates RFI at service layer
ZONE_TRANSITIONS: dict[ZoneStatus, set[ZoneStatus]] = {
    ZoneStatus.NOT_STARTED: {ZoneStatus.IN_PROGRESS},
    ZoneStatus.IN_PROGRESS: {ZoneStatus.COMPLETED, ZoneStatus.BLOCKED},
    ZoneStatus.BLOCKED:     {ZoneStatus.IN_PROGRESS},
    ZoneStatus.COMPLETED:   set(),
}


class WorkZone(ConduitBase):
    __tablename__ = "work_zones"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    systems: Mapped[list[str]] = mapped_column(JSON(), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_STARTED")
    geofence: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    blocked_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    cached_takeoff_items: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON(), nullable=True,
    )
    blocked_rfi_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfis.id"), nullable=True,
    )

    reports: Mapped[list["ZoneProgressReport"]] = relationship(
        "ZoneProgressReport", back_populates="zone", cascade="all, delete-orphan",
        order_by="ZoneProgressReport.created_at",
    )

    def can_transition_to(self, new_status: ZoneStatus) -> bool:
        current = ZoneStatus(self.status)
        return new_status in ZONE_TRANSITIONS.get(current, set())


class ZoneProgressReport(ConduitBase):
    __tablename__ = "zone_progress_reports"

    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_zones.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    reported_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    progress_pct: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    materials_used: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(), nullable=True)
    gps_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    gps_lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)

    zone: Mapped["WorkZone"] = relationship("WorkZone", back_populates="reports")
    photos: Mapped[list["FieldPhoto"]] = relationship(
        "FieldPhoto", back_populates="report", cascade="all, delete-orphan",
    )


class FieldPhoto(ConduitBase):
    __tablename__ = "field_photos"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zone_progress_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    caption: Mapped[str | None] = mapped_column(Text(), nullable=True)

    report: Mapped["ZoneProgressReport"] = relationship("ZoneProgressReport", back_populates="photos")
