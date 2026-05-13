"""
Conduit Backend — Notification Models (M8)
Sprint 5: in-app + email + FCM push routing.

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ConduitBase


class NotificationType(str, enum.Enum):
    PROJECT_INVITATION       = "project_invitation"
    RFI_ASSIGNED             = "rfi_assigned"
    RFI_ANSWERED             = "rfi_answered"
    RFI_APPROACHING_DEADLINE = "rfi_approaching_deadline"
    ZONE_ASSIGNED            = "zone_assigned"
    ZONE_BLOCKED             = "zone_blocked"
    TAKEOFF_COMPLETED        = "takeoff_completed"
    TAKEOFF_REQUIRES_REVIEW  = "takeoff_requires_review"
    PLAN_NEW_VERSION         = "plan_new_version"
    CHANGE_ORDER_PENDING     = "change_order_pending"
    MENTION_IN_COMMENT       = "mention_in_comment"
    LOGIN_NEW_DEVICE         = "login_new_device"


# Default channels per type — applied when user has no explicit preference
EMAIL_DEFAULT_TYPES: set[str] = {
    NotificationType.RFI_ASSIGNED,
    NotificationType.RFI_ANSWERED,
    NotificationType.RFI_APPROACHING_DEADLINE,
    NotificationType.ZONE_BLOCKED,
    NotificationType.TAKEOFF_COMPLETED,
    NotificationType.CHANGE_ORDER_PENDING,
}

PUSH_DEFAULT_TYPES: set[str] = {
    NotificationType.RFI_ASSIGNED,
    NotificationType.ZONE_ASSIGNED,
    NotificationType.ZONE_BLOCKED,
    NotificationType.MENTION_IN_COMMENT,
}


class Notification(ConduitBase):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)


class NotificationPreference(ConduitBase):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    in_app: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    email: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    push: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)


class FCMToken(ConduitBase):
    __tablename__ = "fcm_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="android")
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
