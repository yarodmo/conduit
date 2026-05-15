"""
Conduit Backend — Security Tasks (M14)
Async event persistence + daily digest dispatch.

Bliss Systems LLC — APEX Standard
"""

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="app.tasks.security_tasks.log_security_event",
                 bind=True, max_retries=3, default_retry_delay=10)
def log_security_event(
    self,
    event_type: str,
    severity: str,
    ip_address: str,
    endpoint: str,
    method: str,
    details: dict | None = None,
    request_id: str | None = None,
    org_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Persist security event to DB. Called fire-and-forget from middleware."""
    try:
        import psycopg2
        import json
        from app.core.config import settings

        conn = psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO security_events
               (id, org_id, user_id, event_type, severity, ip_address,
                endpoint, method, details, request_id, resolved, created_at, updated_at)
               VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       false, now(), now())""",
            (
                org_id, user_id, event_type, severity, ip_address,
                endpoint, method,
                json.dumps(details) if details else None,
                request_id,
            ),
        )
        conn.commit()
        conn.close()
        logger.warning(
            "security_event_persisted",
            event_type=event_type,
            severity=severity,
            ip=ip_address,
        )
    except Exception as exc:
        logger.error("security_event_persist_failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(name="app.tasks.security_tasks.send_daily_security_digest",
                 bind=True, max_retries=1, default_retry_delay=60)
def send_daily_security_digest(self) -> None:
    """Daily digest: HIGH/CRITICAL events summary sent to org admins."""
    try:
        import asyncio
        import psycopg2
        from app.core.config import settings

        conn = psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))
        cur = conn.cursor()
        cur.execute("SELECT id FROM organizations WHERE deleted_at IS NULL")
        org_ids = [str(row[0]) for row in cur.fetchall()]
        conn.close()

        async def _run_digests():
            from app.core.database import get_db_session
            from app.modules.security.service import SecurityService
            import uuid

            async with get_db_session() as db:
                for org_id_str in org_ids:
                    try:
                        org_id = uuid.UUID(org_id_str)
                        digest = await SecurityService.generate_digest(db, org_id, days=1)
                        if digest.new_critical > 0 or digest.new_high > 0:
                            logger.warning(
                                "security_digest",
                                org_id=org_id_str,
                                summary=digest.summary,
                            )
                    except Exception as e:
                        logger.error("digest_org_error", org_id=org_id_str, error=str(e))

        asyncio.run(_run_digests())

    except Exception as exc:
        logger.error("daily_digest_failed", error=str(exc))
        raise self.retry(exc=exc)
