"""
Conduit Backend — Report Service (M9)
Async job creation + status polling with presigned S3 URLs.

Flow:
  POST /reports/... → create ReportJob (queued) → enqueue Celery task
  GET  /reports/jobs/{id} → status + presigned download URL when completed

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_presigned_url
from app.models.auth import User
from app.models.reports import ReportJob, ReportStatus, ReportType
from app.modules.reports.schemas import ReportJobResponse


async def _get_job(db: AsyncSession, job_id: uuid.UUID, org_id: uuid.UUID) -> ReportJob:
    stmt = select(ReportJob).where(ReportJob.id == job_id, ReportJob.org_id == org_id)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Report job not found")
    return job


def _to_response(job: ReportJob) -> ReportJobResponse:
    download_url = None
    if job.status == ReportStatus.COMPLETED.value and job.s3_key:
        try:
            download_url = get_presigned_url(job.s3_key)
        except Exception:
            download_url = None

    return ReportJobResponse(
        id=job.id,
        report_type=job.report_type,
        entity_id=job.entity_id,
        status=job.status,
        download_url=download_url,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


class ReportService:

    @staticmethod
    async def create_job(
        db: AsyncSession,
        report_type: ReportType,
        entity_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
    ) -> ReportJobResponse:
        job = ReportJob(
            org_id=org_id,
            created_by=current_user.id,
            report_type=report_type.value,
            entity_id=entity_id,
            status=ReportStatus.QUEUED.value,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        # Enqueue async generation
        try:
            from app.tasks.report_tasks import generate_report
            generate_report.delay(str(job.id))
        except Exception:
            pass  # Job stays queued; worker will pick it up on next poll

        return _to_response(job)

    @staticmethod
    async def get_job(
        db: AsyncSession, job_id: uuid.UUID, org_id: uuid.UUID
    ) -> ReportJobResponse:
        job = await _get_job(db, job_id, org_id)
        return _to_response(job)
