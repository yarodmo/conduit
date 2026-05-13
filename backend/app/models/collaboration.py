"""
Conduit Backend — Collaboration Models (M11)
Multi-user real-time plan markup sessions. Anti-Bluebeam Studio.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ConduitBase

# 10 participant colors — assigned by join order, cycling if >10
PARTICIPANT_COLORS = [
    "#E53935", "#1E88E5", "#43A047", "#FB8C00",
    "#8E24AA", "#00ACC1", "#F4511E", "#3949AB",
    "#00897B", "#6D4C41",
]


class CollabSession(ConduitBase):
    __tablename__ = "collaboration_sessions"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    host_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    session_code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    max_participants: Mapped[int] = mapped_column(Integer(), nullable=False, default=20)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    participants: Mapped[list["SessionParticipant"]] = relationship(
        "SessionParticipant", back_populates="session", cascade="all, delete-orphan",
    )


class SessionParticipant(ConduitBase):
    __tablename__ = "session_participants"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collaboration_sessions.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    color: Mapped[str] = mapped_column(String(10), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    session: Mapped["CollabSession"] = relationship("CollabSession", back_populates="participants")
