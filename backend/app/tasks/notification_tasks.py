"""
Conduit Backend — Notification Tasks (Celery Async, M8)
Handles async email + FCM push dispatch.

Queue: general (worker-general container).

Bliss Systems LLC — APEX Standard
"""

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="app.tasks.notification_tasks.send_notification_email",
                 bind=True, max_retries=3, default_retry_delay=30)
def send_notification_email(self, user_id: str, title: str, body: str) -> None:
    """Send email notification to user. Looks up email from DB via psycopg2."""
    try:
        import psycopg2
        from app.core.config import settings

        if settings.ENVIRONMENT in ("test", "development"):
            logger.info("notif_email_skipped_dev", user_id=user_id, title=title)
            return

        conn = psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))
        cur = conn.cursor()
        cur.execute("SELECT email, full_name FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return

        user_email, full_name = row

        from app.tasks.email_tasks import _send_email
        html_body = f"""
        <html><body>
        <p>Hi {full_name or 'there'},</p>
        <p><strong>{title}</strong></p>
        <p>{body}</p>
        <p style="color:#666;font-size:12px;">— Conduit by Bliss Systems LLC</p>
        </body></html>
        """
        _send_email(user_email, f"[Conduit] {title}", html_body)
        logger.info("notif_email_sent", user_id=user_id, title=title)

    except Exception as exc:
        logger.error("notif_email_failed", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(name="app.tasks.notification_tasks.send_push_notification",
                 bind=True, max_retries=3, default_retry_delay=30)
def send_push_notification(
    self, user_id: str, org_id: str, title: str, body: str, data: dict
) -> None:
    """Send FCM push to all active tokens for user. FCM SDK stub — ready for Sprint 5."""
    try:
        import psycopg2
        from app.core.config import settings

        if settings.ENVIRONMENT in ("test", "development"):
            logger.info("notif_push_skipped_dev", user_id=user_id, title=title)
            return

        conn = psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))
        cur = conn.cursor()
        cur.execute(
            "SELECT token FROM fcm_tokens WHERE user_id = %s AND org_id = %s AND is_active = true",
            (user_id, org_id),
        )
        tokens = [row[0] for row in cur.fetchall()]
        conn.close()

        if not tokens:
            return

        # FCM dispatch stub — integrate firebase-admin SDK in Sprint 5 when Flutter ships
        for token in tokens:
            logger.info("notif_push_would_send", token=token[:20], title=title)

    except Exception as exc:
        logger.error("notif_push_failed", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc)
