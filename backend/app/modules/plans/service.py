"""
Conduit Backend — Plan Service (M3 + M4)
Business logic: upload, status, metadata, tile serving.

Bliss Systems LLC — APEX Standard
"""

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.storage import (
    get_presigned_url,
    object_exists,
    plan_tile_key,
    upload_fileobj,
    plan_original_key,
    plan_page_thumb_key,
    plan_page_full_key,
)
from app.models.auth import User
from app.models.plans import Plan, PlanPage, PlanProcessingJob, PlanSourceType
from app.modules.plans.schemas import (
    PlanListItem,
    PlanMetadataResponse,
    PlanPageResponse,
    PlanUploadResponse,
    ProcessingJobStatus,
)

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".heic", ".webp"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


def _detect_source_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return PlanSourceType.pdf.value
    return PlanSourceType.phone_photo.value


def _page_url(key: str | None) -> str:
    if not key:
        return ""
    return get_presigned_url(settings.S3_BUCKET_PLANS, key)


class PlanService:

    @staticmethod
    async def upload(
        db: AsyncSession,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        file: UploadFile,
        name: str | None,
    ) -> PlanUploadResponse:
        ext = Path(file.filename or "plan.pdf").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported file type '{ext}'. Allowed: {ALLOWED_EXTENSIONS}",
            )

        display_name = name or Path(file.filename or "Unnamed Plan").stem
        source_type = _detect_source_type(file.filename or "")

        # STEP 0 — Create plan + job records immediately
        plan = Plan(
            org_id=org_id,
            project_id=project_id,
            uploaded_by=current_user.id,
            name=display_name,
            original_filename=file.filename or "plan",
            source_type=source_type,
            status="uploading",
        )
        db.add(plan)
        await db.flush()  # get plan.id without committing

        job = PlanProcessingJob(plan_id=plan.id, status="queued", progress_pct=0)
        db.add(job)
        await db.flush()

        # Upload original to S3
        s3_key = plan_original_key(str(org_id), str(project_id), str(plan.id), ext.lstrip("."))
        file.file.seek(0)
        upload_fileobj(file.file, settings.S3_BUCKET_PLANS, s3_key,
                       content_type=file.content_type or "application/octet-stream")

        # Update plan with S3 key
        plan.s3_key_original = s3_key
        plan.status = "queued"
        job.status = "queued"

        await db.commit()
        await db.refresh(plan)
        await db.refresh(job)

        # Dispatch Celery pipeline (non-blocking)
        from app.tasks.plan_tasks import dispatch_plan_processing
        celery_id = dispatch_plan_processing(
            plan_id=str(plan.id),
            job_id=str(job.id),
            org_id=str(org_id),
            project_id=str(project_id),
            source_type=source_type,
        )
        job.celery_task_id = celery_id
        await db.commit()

        return PlanUploadResponse(
            plan_id=plan.id,
            job_id=job.id,
            status="queued",
            message="Plan uploaded. Processing started.",
        )

    @staticmethod
    async def get_status(
        db: AsyncSession,
        plan_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> ProcessingJobStatus:
        stmt = (
            select(PlanProcessingJob)
            .join(Plan, PlanProcessingJob.plan_id == Plan.id)
            .where(Plan.id == plan_id, Plan.org_id == org_id)
            .order_by(PlanProcessingJob.created_at.desc())
            .limit(1)
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Plan or job not found")

        return ProcessingJobStatus(
            job_id=job.id,
            plan_id=job.plan_id,
            status=job.status,
            current_step=job.current_step,
            progress_pct=job.progress_pct,
            error_message=job.error_message,
        )

    @staticmethod
    async def get_metadata(
        db: AsyncSession,
        plan_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> PlanMetadataResponse:
        stmt = (
            select(Plan)
            .options(selectinload(Plan.pages))
            .where(Plan.id == plan_id, Plan.org_id == org_id, Plan.deleted_at.is_(None))
        )
        plan = (await db.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        pages = [
            PlanPageResponse(
                page_number=p.page_number,
                thumb_url=_page_url(p.s3_key_thumb),
                full_url=_page_url(p.s3_key_full),
                width_px=p.width_px,
                height_px=p.height_px,
                orientation=p.orientation,
            )
            for p in plan.pages
        ]

        return PlanMetadataResponse(
            id=plan.id,
            project_id=plan.project_id,
            name=plan.name,
            original_filename=plan.original_filename,
            source_type=plan.source_type,
            status=plan.status,
            total_pages=plan.total_pages,
            plan_type=plan.plan_type,
            scale_text=plan.scale_text,
            plan_number=plan.plan_number,
            plan_title=plan.plan_title,
            plan_date=plan.plan_date,
            plan_revision=plan.plan_revision,
            color_legend=plan.color_legend,
            complexity_score=plan.complexity_score,
            quality_score=plan.quality_score,
            deskew_applied=plan.deskew_applied,
            pages=pages,
        )

    @staticmethod
    async def list_plans(
        db: AsyncSession,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> list[PlanListItem]:
        stmt = (
            select(Plan)
            .options(selectinload(Plan.pages))
            .where(
                Plan.project_id == project_id,
                Plan.org_id == org_id,
                Plan.deleted_at.is_(None),
            )
            .order_by(Plan.created_at.desc())
        )
        plans = (await db.execute(stmt)).scalars().all()

        result = []
        for plan in plans:
            thumb = None
            if plan.pages:
                thumb = _page_url(plan.pages[0].s3_key_thumb)
            result.append(PlanListItem(
                id=plan.id,
                name=plan.name,
                original_filename=plan.original_filename,
                source_type=plan.source_type,
                status=plan.status,
                total_pages=plan.total_pages,
                plan_type=plan.plan_type,
                complexity_score=plan.complexity_score,
                thumb_url=thumb,
            ))
        return result

    @staticmethod
    async def get_tile(
        db: AsyncSession,
        plan_id: uuid.UUID,
        org_id: uuid.UUID,
        page: int,
        zoom: int,
        x: int,
        y: int,
    ) -> bytes:
        # Verify plan belongs to org
        stmt = select(Plan).where(
            Plan.id == plan_id, Plan.org_id == org_id, Plan.deleted_at.is_(None)
        )
        plan = (await db.execute(stmt)).scalar_one_or_none()
        if not plan or plan.status != "ready":
            raise HTTPException(status_code=404, detail="Plan not found or not ready")

        if zoom < 0 or zoom > 3:
            raise HTTPException(status_code=400, detail="Zoom must be 0-3")

        key = plan_tile_key(str(plan_id), page, zoom, x, y)

        # Serve from S3 (or local dev) directly
        from app.core.storage import download_bytes
        try:
            return download_bytes(settings.S3_BUCKET_PLANS, key)
        except FileNotFoundError:
            pass

        # Tile not pre-generated — generate on demand for zoom > 1
        if zoom >= 2:
            from app.tasks.plan_tasks import generate_tile_on_demand
            generate_tile_on_demand.apply_async(
                args=[str(plan_id), str(org_id), str(plan.project_id), page, zoom, x, y],
                countdown=0,
            )

        raise HTTPException(
            status_code=404,
            detail="Tile not ready. Retry in a moment.",
        )
