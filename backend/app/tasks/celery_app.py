"""
Conduit Backend — Celery Application Configuration
Prompt 3: "Emails siempre a Celery queue, nunca síncronos"

Queue topology matches Docker container layout:
  - general: worker-general (emails, notifications)
  - ai: worker-ai (Claude API calls)
  - plans: worker-plans (PDF processing, OCR, tiles)

Serializer: JSON only (security — no pickle).
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "conduit",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    # Security: JSON only — never pickle
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Queue routing — maps to Docker containers
    task_routes={
        "app.tasks.email_tasks.*": {"queue": "general"},
        "app.tasks.ai_tasks.*": {"queue": "ai"},
        "app.tasks.plan_tasks.*": {"queue": "plans"},
    },

    # Default queue
    task_default_queue="general",

    # Retry policy
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Result expiry
    result_expires=3600,  # 1 hour

    # Concurrency per worker type
    worker_concurrency=4,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])
