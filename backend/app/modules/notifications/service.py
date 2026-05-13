"""
Conduit Backend — Notification Service (M8)
Multi-channel dispatch: in_app + email (Celery) + FCM push (Celery).
Redis Pub/Sub for real-time badge updates.

Bliss Systems LLC — APEX Standard
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.notifications import (
    EMAIL_DEFAULT_TYPES, PUSH_DEFAULT_TYPES,
    FCMToken, Notification, NotificationPreference, NotificationType,
)
from app.modules.notifications.schemas import (
    ChannelPreference,
    FCMTokenCreate,
    FCMTokenResponse,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationResponse,
    UnreadCountResponse,
)

logger = structlog.get_logger()

ALL_TYPES = [t.value for t in NotificationType]


# ── Defaults ───────────────────────────────────────────────────────────────

def _default_pref(notif_type: str) -> ChannelPreference:
    return ChannelPreference(
        in_app=True,
        email=notif_type in EMAIL_DEFAULT_TYPES,
        push=notif_type in PUSH_DEFAULT_TYPES,
    )


def _build_prefs_response(
    db_prefs: list[NotificationPreference],
) -> NotificationPreferencesResponse:
    pref_map: dict[str, ChannelPreference] = {
        p.type: ChannelPreference(in_app=p.in_app, email=p.email, push=p.push)
        for p in db_prefs
    }
    kwargs = {}
    for t in ALL_TYPES:
        kwargs[t] = pref_map.get(t, _default_pref(t))
    return NotificationPreferencesResponse(**kwargs)


# ── Core send_notification ─────────────────────────────────────────────────

async def send_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    notif_type: NotificationType,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> None:
    """
    Dispatch a notification through all enabled channels.
    Called internally from RFI/Field/Takeoff services.
    """
    # 1. Always create in-app record
    notif = Notification(
        user_id=user_id,
        org_id=org_id,
        type=notif_type.value,
        title=title,
        body=body,
        data=data,
    )
    db.add(notif)
    await db.flush()

    # 2. Fetch user preferences (or fall back to defaults)
    pref_stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == user_id,
        NotificationPreference.org_id == org_id,
        NotificationPreference.type == notif_type.value,
    )
    pref = (await db.execute(pref_stmt)).scalar_one_or_none()

    email_enabled = pref.email if pref else (notif_type.value in EMAIL_DEFAULT_TYPES)
    push_enabled = pref.push if pref else (notif_type.value in PUSH_DEFAULT_TYPES)

    # 3. Queue async tasks (fire and forget — tasks will DB-query user email/tokens)
    if email_enabled:
        try:
            from app.tasks.notification_tasks import send_notification_email
            send_notification_email.delay(str(user_id), title, body)
        except Exception:
            logger.warning("notif_email_queue_failed", user_id=str(user_id))

    if push_enabled:
        try:
            from app.tasks.notification_tasks import send_push_notification
            send_push_notification.delay(str(user_id), str(org_id), title, body,
                                         data or {})
        except Exception:
            logger.warning("notif_push_queue_failed", user_id=str(user_id))

    # 4. Publish to Redis Pub/Sub for real-time badge update
    try:
        from app.core.redis import redis_client
        if redis_client:
            payload = json.dumps({"type": "notification", "unread_delta": 1})
            await redis_client.publish(f"ws:user:{user_id}", payload)
    except Exception:
        logger.warning("notif_redis_publish_failed", user_id=str(user_id))

    logger.info("notification_sent", user_id=str(user_id), type=notif_type.value)


# ── Notification CRUD ──────────────────────────────────────────────────────

class NotificationService:

    @staticmethod
    async def list_notifications(
        db: AsyncSession,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> NotificationListResponse:
        base = and_(
            Notification.user_id == user_id,
            Notification.org_id == org_id,
            Notification.is_deleted.is_(False),
        )
        count_stmt = select(func.count()).where(base)
        total = (await db.execute(count_stmt)).scalar_one()

        unread_stmt = select(func.count()).where(
            base, Notification.is_read.is_(False)
        )
        unread_count = (await db.execute(unread_stmt)).scalar_one()

        items_stmt = (
            select(Notification)
            .where(base)
            .order_by(Notification.is_read.asc(), Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = (await db.execute(items_stmt)).scalars().all()

        return NotificationListResponse(
            items=[NotificationResponse.model_validate(n) for n in items],
            total=total,
            unread_count=unread_count,
        )

    @staticmethod
    async def unread_count(
        db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> UnreadCountResponse:
        stmt = select(func.count()).where(
            Notification.user_id == user_id,
            Notification.org_id == org_id,
            Notification.is_read.is_(False),
            Notification.is_deleted.is_(False),
        )
        count = (await db.execute(stmt)).scalar_one()
        return UnreadCountResponse(unread_count=count)

    @staticmethod
    async def mark_read(
        db: AsyncSession,
        notif_id: uuid.UUID,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> NotificationResponse:
        notif = await db.get(Notification, notif_id)
        if not notif or notif.user_id != user_id or notif.is_deleted:
            raise HTTPException(status_code=404, detail="Notification not found")
        notif.is_read = True
        await db.commit()
        await db.refresh(notif)
        return NotificationResponse.model_validate(notif)

    @staticmethod
    async def mark_all_read(
        db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> dict[str, int]:
        from sqlalchemy import update
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.org_id == org_id,
                Notification.is_read.is_(False),
                Notification.is_deleted.is_(False),
            )
            .values(is_read=True)
        )
        result = await db.execute(stmt)
        await db.commit()
        return {"marked": result.rowcount}

    @staticmethod
    async def delete_notification(
        db: AsyncSession,
        notif_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        notif = await db.get(Notification, notif_id)
        if not notif or notif.user_id != user_id:
            raise HTTPException(status_code=404, detail="Notification not found")
        notif.is_deleted = True
        await db.commit()

    # ── Preferences ──────────────────────────────────────────────────────

    @staticmethod
    async def get_preferences(
        db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> NotificationPreferencesResponse:
        stmt = select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.org_id == org_id,
        )
        prefs = (await db.execute(stmt)).scalars().all()
        return _build_prefs_response(list(prefs))

    @staticmethod
    async def update_preferences(
        db: AsyncSession,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        data: NotificationPreferencesUpdate,
    ) -> NotificationPreferencesResponse:
        updates = data.model_dump(exclude_none=True)
        now = datetime.now(tz=timezone.utc)

        for notif_type_str, channels in updates.items():
            stmt = select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.org_id == org_id,
                NotificationPreference.type == notif_type_str,
            )
            pref = (await db.execute(stmt)).scalar_one_or_none()

            if pref:
                pref.in_app = channels["in_app"]
                pref.email = channels["email"]
                pref.push = channels["push"]
                pref.updated_at = now
            else:
                pref = NotificationPreference(
                    user_id=user_id,
                    org_id=org_id,
                    type=notif_type_str,
                    in_app=channels["in_app"],
                    email=channels["email"],
                    push=channels["push"],
                )
                db.add(pref)

        await db.commit()
        return await NotificationService.get_preferences(db, user_id, org_id)


# ── FCM Token service ──────────────────────────────────────────────────────

class FCMTokenService:

    @staticmethod
    async def register(
        db: AsyncSession,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        data: FCMTokenCreate,
    ) -> FCMTokenResponse:
        # Upsert — same token from same device re-activates
        stmt = select(FCMToken).where(FCMToken.token == data.token)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        now = datetime.now(tz=timezone.utc)

        if existing:
            existing.user_id = user_id
            existing.org_id = org_id
            existing.is_active = True
            existing.last_used_at = now
            if data.device_name:
                existing.device_name = data.device_name
            await db.commit()
            await db.refresh(existing)
            return FCMTokenResponse.model_validate(existing)

        token = FCMToken(
            user_id=user_id,
            org_id=org_id,
            token=data.token,
            device_name=data.device_name,
            platform=data.platform,
            last_used_at=now,
        )
        db.add(token)
        await db.commit()
        await db.refresh(token)
        return FCMTokenResponse.model_validate(token)

    @staticmethod
    async def invalidate(
        db: AsyncSession, token_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        token = await db.get(FCMToken, token_id)
        if not token or token.user_id != user_id:
            raise HTTPException(status_code=404, detail="FCM token not found")
        token.is_active = False
        await db.commit()

    @staticmethod
    async def list_tokens(
        db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> list[FCMTokenResponse]:
        stmt = select(FCMToken).where(
            FCMToken.user_id == user_id,
            FCMToken.org_id == org_id,
            FCMToken.is_active.is_(True),
        ).order_by(FCMToken.last_used_at.desc())
        tokens = (await db.execute(stmt)).scalars().all()
        return [FCMTokenResponse.model_validate(t) for t in tokens]
