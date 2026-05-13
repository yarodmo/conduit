"""
Conduit Backend — Notifications Router (M8)

Notifications:
  GET    /notifications                   → paginated list (unread first)
  GET    /notifications/unread-count      → badge count
  PATCH  /notifications/{id}/mark-read    → mark single read
  POST   /notifications/mark-all-read     → mark all read
  DELETE /notifications/{id}              → soft-delete

Preferences:
  GET    /notifications/preferences       → user channel prefs
  PUT    /notifications/preferences       → update prefs per type

FCM Tokens:
  POST   /devices/fcm-token              → register device token
  DELETE /devices/fcm-token/{token_id}   → invalidate token
  GET    /devices/fcm-tokens             → list active devices

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.notifications.schemas import (
    FCMTokenCreate,
    FCMTokenResponse,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationResponse,
    UnreadCountResponse,
)
from app.modules.notifications.service import FCMTokenService, NotificationService

router = APIRouter(tags=["Notifications"])


# ── Notifications ──────────────────────────────────────────────────────────

@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> NotificationListResponse:
    return await NotificationService.list_notifications(
        db, current_user.id, org.id, page, page_size
    )


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> UnreadCountResponse:
    return await NotificationService.unread_count(db, current_user.id, org.id)


@router.post("/notifications/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    return await NotificationService.mark_all_read(db, current_user.id, org.id)


@router.patch("/notifications/{notif_id}/mark-read", response_model=NotificationResponse)
async def mark_read(
    notif_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> NotificationResponse:
    return await NotificationService.mark_read(db, notif_id, current_user.id, org.id)


@router.delete("/notifications/{notif_id}", status_code=204)
async def delete_notification(
    notif_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: Organization = Depends(get_current_org),
) -> None:
    await NotificationService.delete_notification(db, notif_id, current_user.id)


# ── Preferences ────────────────────────────────────────────────────────────

@router.get("/notifications/preferences", response_model=NotificationPreferencesResponse)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> NotificationPreferencesResponse:
    return await NotificationService.get_preferences(db, current_user.id, org.id)


@router.put("/notifications/preferences", response_model=NotificationPreferencesResponse)
async def update_preferences(
    data: NotificationPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> NotificationPreferencesResponse:
    return await NotificationService.update_preferences(db, current_user.id, org.id, data)


# ── FCM Tokens ─────────────────────────────────────────────────────────────

@router.post("/devices/fcm-token", response_model=FCMTokenResponse, status_code=201)
async def register_fcm_token(
    data: FCMTokenCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> FCMTokenResponse:
    return await FCMTokenService.register(db, current_user.id, org.id, data)


@router.delete("/devices/fcm-token/{token_id}", status_code=204)
async def invalidate_fcm_token(
    token_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: Organization = Depends(get_current_org),
) -> None:
    await FCMTokenService.invalidate(db, token_id, current_user.id)


@router.get("/devices/fcm-tokens", response_model=list[FCMTokenResponse])
async def list_fcm_tokens(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[FCMTokenResponse]:
    return await FCMTokenService.list_tokens(db, current_user.id, org.id)
