"""Conduit Backend — Notification Schemas (M8). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Notification ──────────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str
    data: dict[str, Any] | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


# ── Preferences ───────────────────────────────────────────────────────────

class ChannelPreference(BaseModel):
    in_app: bool = True
    email: bool = True
    push: bool = True


class NotificationPreferencesUpdate(BaseModel):
    project_invitation: ChannelPreference | None = None
    rfi_assigned: ChannelPreference | None = None
    rfi_answered: ChannelPreference | None = None
    rfi_approaching_deadline: ChannelPreference | None = None
    zone_assigned: ChannelPreference | None = None
    zone_blocked: ChannelPreference | None = None
    takeoff_completed: ChannelPreference | None = None
    takeoff_requires_review: ChannelPreference | None = None
    plan_new_version: ChannelPreference | None = None
    change_order_pending: ChannelPreference | None = None
    mention_in_comment: ChannelPreference | None = None
    login_new_device: ChannelPreference | None = None


class NotificationPreferencesResponse(BaseModel):
    project_invitation: ChannelPreference
    rfi_assigned: ChannelPreference
    rfi_answered: ChannelPreference
    rfi_approaching_deadline: ChannelPreference
    zone_assigned: ChannelPreference
    zone_blocked: ChannelPreference
    takeoff_completed: ChannelPreference
    takeoff_requires_review: ChannelPreference
    plan_new_version: ChannelPreference
    change_order_pending: ChannelPreference
    mention_in_comment: ChannelPreference
    login_new_device: ChannelPreference


# ── FCM Tokens ────────────────────────────────────────────────────────────

class FCMTokenCreate(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    device_name: str | None = None
    platform: str = "android"


class FCMTokenResponse(BaseModel):
    id: uuid.UUID
    token: str
    device_name: str | None
    platform: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
