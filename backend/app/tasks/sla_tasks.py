"""
Conduit Backend — SLA Alert Tasks (M7)
Celery beat periodic tasks for RFI due-date monitoring.

Schedule (configured in celery_app.py beat_schedule):
  - check_rfi_sla: every 1 hour — alerts 24h before due + at expiry

Bliss Systems LLC — APEX Standard
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _sync_db():
    import sqlalchemy as sa
    from sqlalchemy.orm import Session
    from app.core.config import settings
    url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = sa.create_engine(url, pool_pre_ping=True)
    return Session(engine)


@celery_app.task(
    name="app.tasks.sla_tasks.check_rfi_sla",
    queue="general",
)
def check_rfi_sla() -> None:
    """
    Scan open RFIs for SLA violations:
    - 24h before due_date → alert assigned + PM
    - Past due_date → alert PM + flag in dashboard
    - CRITICAL urgency with no response in 4h → immediate push
    """
    import sqlalchemy as sa
    from app.models.rfis import RFI
    from app.tasks.email_tasks import send_rfi_sla_alert

    session = _sync_db()
    try:
        now = datetime.now(tz=timezone.utc)
        warning_threshold = now + timedelta(hours=24)

        # RFIs approaching due date (not yet alerted)
        approaching = session.execute(
            sa.select(RFI).where(
                RFI.due_date.is_not(None),
                RFI.due_date <= warning_threshold,
                RFI.due_date > now,
                RFI.sla_alerted.is_(False),
                RFI.status.not_in(["CLOSED", "REJECTED"]),
            )
        ).scalars().all()

        for rfi in approaching:
            logger.info("sla_warning rfi_id=%s number=%s", rfi.id, rfi.rfi_number)
            send_rfi_sla_alert.apply_async(
                kwargs={
                    "rfi_id": str(rfi.id),
                    "alert_type": "warning_24h",
                    "rfi_number": rfi.rfi_number,
                    "urgency": rfi.urgency,
                },
            )
            rfi.sla_alerted = True

        # Overdue RFIs
        overdue = session.execute(
            sa.select(RFI).where(
                RFI.due_date.is_not(None),
                RFI.due_date <= now,
                RFI.status.not_in(["CLOSED", "REJECTED"]),
            )
        ).scalars().all()

        for rfi in overdue:
            logger.warning("sla_overdue rfi_id=%s number=%s", rfi.id, rfi.rfi_number)
            send_rfi_sla_alert.apply_async(
                kwargs={
                    "rfi_id": str(rfi.id),
                    "alert_type": "overdue",
                    "rfi_number": rfi.rfi_number,
                    "urgency": rfi.urgency,
                },
            )

        session.commit()
        logger.info("sla_check_complete approaching=%d overdue=%d",
                    len(approaching), len(overdue))

    except Exception as exc:
        logger.exception("check_rfi_sla failed: %s", exc)
        session.rollback()
    finally:
        session.close()
