"""
Conduit Backend — Self-Learning Pipeline Tasks (M13)
Nightly Celery beat: analyze corrections, update accuracy scores, alert on low accuracy.

Schedule: every 24 hours (86400s), runs on worker-general.

Bliss Systems LLC — APEX Standard
"""

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="app.tasks.learning_tasks.run_learning_analysis",
                 bind=True, max_retries=1, default_retry_delay=300)
def run_learning_analysis(self) -> None:
    """
    Nightly task: analyze all orgs' correction patterns.
    Runs via Celery beat every 24h.
    """
    try:
        import asyncio
        import psycopg2
        from app.core.config import settings

        # Get all active org IDs
        conn = psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))
        cur = conn.cursor()
        cur.execute("SELECT id FROM organizations WHERE deleted_at IS NULL")
        org_ids = [str(row[0]) for row in cur.fetchall()]
        conn.close()

        if not org_ids:
            logger.info("learning_no_orgs")
            return

        async def _analyze_all():
            from app.core.database import get_db_session
            from app.modules.learning.service import LearningService
            import uuid

            async with get_db_session() as db:
                for org_id_str in org_ids:
                    try:
                        org_id = uuid.UUID(org_id_str)
                        result = await LearningService.run_analysis(db, org_id)
                        logger.info(
                            "learning_org_analyzed",
                            org_id=org_id_str,
                            corrections=result.summary[:80],
                        )
                    except Exception as e:
                        logger.error("learning_org_error", org_id=org_id_str, error=str(e))

        asyncio.run(_analyze_all())

    except Exception as exc:
        logger.error("learning_task_failed", error=str(exc))
        raise self.retry(exc=exc)
