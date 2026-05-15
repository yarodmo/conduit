"""
Conduit Backend — Security Monitor Service (M14)
Event CRUD, stats aggregation, alert dispatch.

Bliss Systems LLC — APEX Standard
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import SecurityEvent, SecurityEventType, SecuritySeverity, SEVERITY_MAP
from app.modules.security.schemas import (
    SecurityDigestResponse,
    SecurityEventResponse,
    SecurityStatsResponse,
)

logger = structlog.get_logger()


def _to_response(event: SecurityEvent) -> SecurityEventResponse:
    return SecurityEventResponse.model_validate(event)


class SecurityService:

    @staticmethod
    async def log_event(
        db: AsyncSession,
        event_type: str,
        severity: str,
        ip_address: str,
        endpoint: str,
        method: str,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
        org_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> SecurityEvent:
        event = SecurityEvent(
            org_id=org_id,
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            ip_address=ip_address,
            endpoint=endpoint,
            method=method,
            details=details,
            request_id=request_id,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)

        # Alert on CRITICAL or HIGH events
        if severity in ("CRITICAL", "HIGH"):
            await _dispatch_security_alert(db, event)

        logger.warning(
            "security_event_logged",
            event_type=event_type,
            severity=severity,
            ip=ip_address,
            endpoint=endpoint,
        )
        return event

    @staticmethod
    async def list_events(
        db: AsyncSession,
        org_id: uuid.UUID | None = None,
        severity: str | None = None,
        event_type: str | None = None,
        unresolved_only: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> list[SecurityEventResponse]:
        filters = []
        if org_id:
            filters.append(SecurityEvent.org_id == org_id)
        if severity:
            filters.append(SecurityEvent.severity == severity)
        if event_type:
            filters.append(SecurityEvent.event_type == event_type)
        if unresolved_only:
            filters.append(SecurityEvent.resolved.is_(False))

        from sqlalchemy import and_
        stmt = (
            select(SecurityEvent)
            .where(and_(*filters) if filters else True)
            .order_by(SecurityEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        events = (await db.execute(stmt)).scalars().all()
        return [_to_response(e) for e in events]

    @staticmethod
    async def get_stats(
        db: AsyncSession,
        org_id: uuid.UUID | None = None,
        days: int = 7,
    ) -> SecurityStatsResponse:
        since = datetime.now(tz=timezone.utc) - timedelta(days=days)
        base_filter = [SecurityEvent.created_at >= since]
        if org_id:
            base_filter.append(SecurityEvent.org_id == org_id)

        from sqlalchemy import and_
        base = and_(*base_filter)

        total_stmt = select(func.count()).where(base)
        total = (await db.execute(total_stmt)).scalar_one()

        critical_stmt = select(func.count()).where(
            base, SecurityEvent.severity == "CRITICAL"
        )
        critical = (await db.execute(critical_stmt)).scalar_one()

        high_stmt = select(func.count()).where(base, SecurityEvent.severity == "HIGH")
        high = (await db.execute(high_stmt)).scalar_one()

        unresolved_critical_stmt = select(func.count()).where(
            base,
            SecurityEvent.severity == "CRITICAL",
            SecurityEvent.resolved.is_(False),
        )
        unresolved_critical = (await db.execute(unresolved_critical_stmt)).scalar_one()

        # By type
        type_stmt = (
            select(SecurityEvent.event_type, func.count())
            .where(base)
            .group_by(SecurityEvent.event_type)
        )
        by_type = {row[0]: row[1] for row in (await db.execute(type_stmt)).all()}

        # Top IPs (max 5)
        ip_stmt = (
            select(SecurityEvent.ip_address, func.count().label("cnt"))
            .where(base)
            .group_by(SecurityEvent.ip_address)
            .order_by(func.count().desc())
            .limit(5)
        )
        top_ips = [
            {"ip": row[0], "count": row[1]}
            for row in (await db.execute(ip_stmt)).all()
        ]

        return SecurityStatsResponse(
            period_days=days,
            total_events=total,
            critical_events=critical,
            high_events=high,
            unresolved_critical=unresolved_critical,
            by_type=by_type,
            top_ips=top_ips,
        )

    @staticmethod
    async def resolve_event(
        db: AsyncSession, event_id: uuid.UUID
    ) -> SecurityEventResponse:
        event = await db.get(SecurityEvent, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Security event not found")
        event.resolved = True
        event.resolved_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(event)
        return _to_response(event)

    @staticmethod
    async def generate_digest(
        db: AsyncSession,
        org_id: uuid.UUID | None = None,
        days: int = 1,
    ) -> SecurityDigestResponse:
        stats = await SecurityService.get_stats(db, org_id, days)
        top_attackers = [ip["ip"] for ip in stats.top_ips[:3]]

        if stats.total_events == 0:
            summary = f"No security events in the last {days} day(s). System clean."
        else:
            parts = [f"{stats.total_events} events detected."]
            if stats.critical_events:
                parts.append(f"⚠️ {stats.critical_events} CRITICAL.")
            if stats.high_events:
                parts.append(f"{stats.high_events} HIGH severity.")
            if stats.unresolved_critical:
                parts.append(f"{stats.unresolved_critical} unresolved critical events.")
            summary = " ".join(parts)

        return SecurityDigestResponse(
            period_days=days,
            total_events=stats.total_events,
            new_critical=stats.critical_events,
            new_high=stats.high_events,
            top_attackers=top_attackers,
            summary=summary,
        )


async def _dispatch_security_alert(
    db: AsyncSession, event: SecurityEvent
) -> None:
    """Notify org admins on HIGH/CRITICAL events."""
    try:
        if not event.org_id:
            return
        from app.models.auth import OrgRole, OrganizationMember
        from app.models.notifications import NotificationType
        from app.modules.notifications.service import send_notification

        stmt = select(OrganizationMember).where(
            OrganizationMember.org_id == event.org_id,
            OrganizationMember.role == OrgRole.ORG_ADMIN,
        )
        members = (await db.execute(stmt)).scalars().all()

        for member in members:
            await send_notification(
                db=db,
                user_id=member.user_id,
                org_id=event.org_id,
                notif_type=NotificationType.LOGIN_NEW_DEVICE,
                title=f"[{event.severity}] Security Alert: {event.event_type}",
                body=f"Attack detected from {event.ip_address} on {event.endpoint}",
                data={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "severity": event.severity,
                },
            )
    except Exception:
        pass  # Non-critical — don't block event logging
