"""
Conduit Backend — RFI & Markup Models (M7)
Sprint 3: Markup → RFI → Change Order contractual flow.

State machine enforced at service layer (not DB — allows audit trail).

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


class MarkupType(str, enum.Enum):
    ARROW = "ARROW"
    RECTANGLE = "RECTANGLE"
    CIRCLE = "CIRCLE"
    FREEHAND = "FREEHAND"
    TEXT = "TEXT"
    CLOUD = "CLOUD"        # AEC standard — triggers RFI prompt
    DIMENSION = "DIMENSION"


class RFIStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ANSWERED = "ANSWERED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class RFIUrgency(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RFISource(str, enum.Enum):
    MARKUP_ESCALATED = "MARKUP_ESCALATED"
    MANUAL = "MANUAL"
    FIELD_BLOCKED = "FIELD_BLOCKED"
    AI_DETECTED = "AI_DETECTED"


class COStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Valid transitions — enforced strictly, no state skipping
RFI_TRANSITIONS: dict[RFIStatus, set[RFIStatus]] = {
    RFIStatus.DRAFT:        {RFIStatus.SUBMITTED},
    RFIStatus.SUBMITTED:    {RFIStatus.UNDER_REVIEW},
    RFIStatus.UNDER_REVIEW: {RFIStatus.ANSWERED, RFIStatus.CLOSED},
    RFIStatus.ANSWERED:     {RFIStatus.CLOSED, RFIStatus.REJECTED},
    RFIStatus.REJECTED:     {RFIStatus.UNDER_REVIEW},
    RFIStatus.CLOSED:       set(),
}


class Markup(ConduitBase):
    __tablename__ = "markups"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    coordinates: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#FF0000")
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_number: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    resolved: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    rfi: Mapped["RFI | None"] = relationship("RFI", back_populates="markup", uselist=False)


class RFI(ConduitBase):
    __tablename__ = "rfis"

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
    markup_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("markups.id"), nullable=True,
    )
    rfi_number: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    urgency: Mapped[str] = mapped_column(String(10), nullable=False, default="MEDIUM")
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="MANUAL")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_alerted: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    markup: Mapped["Markup | None"] = relationship("Markup", back_populates="rfi")
    comments: Mapped[list["RFIComment"]] = relationship(
        "RFIComment", back_populates="rfi", cascade="all, delete-orphan",
        order_by="RFIComment.created_at",
    )
    change_order: Mapped["ChangeOrder | None"] = relationship(
        "ChangeOrder", back_populates="rfi", uselist=False,
    )

    def can_transition_to(self, new_status: RFIStatus) -> bool:
        current = RFIStatus(self.status)
        return new_status in RFI_TRANSITIONS.get(current, set())


class RFIComment(ConduitBase):
    __tablename__ = "rfi_comments"

    rfi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfis.id", ondelete="CASCADE"), nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    is_official_response: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    rfi: Mapped["RFI"] = relationship("RFI", back_populates="comments")


class ChangeOrder(ConduitBase):
    __tablename__ = "change_orders"

    rfi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfis.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    co_number: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_change_description: Mapped[str] = mapped_column(Text(), nullable=False)
    cost_impact_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    time_impact_days: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    affected_systems: Mapped[list[str] | None] = mapped_column(JSON(), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pdf_s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    rfi: Mapped["RFI"] = relationship("RFI", back_populates="change_order")
