"""
Conduit Backend — Takeoff Service (M5)

Bliss Systems LLC — APEX Standard
"""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import User
from app.models.plans import Plan, PlanPage
from app.models.takeoff import MaterialCatalog, TakeoffItem, TakeoffJob
from app.modules.takeoff.schemas import (
    CostPreviewResponse,
    TakeoffInitResponse,
    TakeoffItemCreate,
    TakeoffItemResponse,
    TakeoffItemUpdate,
    TakeoffJobDetailResponse,
    TakeoffJobResponse,
    TakeoffSummaryResponse,
    CostBreakdown,
)
from app.tasks.ai_tasks import estimate_cost


class TakeoffService:

    @staticmethod
    async def cost_preview(
        db: AsyncSession,
        plan_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> CostPreviewResponse:
        stmt = select(Plan).where(
            Plan.id == plan_id, Plan.org_id == org_id, Plan.deleted_at.is_(None)
        )
        plan = (await db.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        if plan.status != "ready":
            raise HTTPException(status_code=422, detail="Plan must be fully processed before takeoff")

        # Get first page dimensions
        page_stmt = select(PlanPage).where(
            PlanPage.plan_id == plan_id, PlanPage.page_number == 1
        )
        page = (await db.execute(page_stmt)).scalar_one_or_none()
        w = page.width_px if page and page.width_px else 2550
        h = page.height_px if page and page.height_px else 3300

        est = estimate_cost(w, h)
        return CostPreviewResponse(
            plan_id=plan_id,
            sections=est["sections"],
            estimated_input_tokens=est["estimated_input_tokens"],
            estimated_output_tokens=est["estimated_output_tokens"],
            estimated_cost_usd=est["estimated_cost_usd"],
            message=f"Estimated ${est['estimated_cost_usd']:.4f} USD for {est['sections']} section(s). Confirm to proceed.",
        )

    @staticmethod
    async def initiate(
        db: AsyncSession,
        plan_id: uuid.UUID,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        current_user: User,
    ) -> TakeoffInitResponse:
        stmt = select(Plan).where(
            Plan.id == plan_id, Plan.org_id == org_id, Plan.deleted_at.is_(None)
        )
        plan = (await db.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        if plan.status != "ready":
            raise HTTPException(status_code=422, detail="Plan must be ready before takeoff")

        page_stmt = select(PlanPage).where(
            PlanPage.plan_id == plan_id, PlanPage.page_number == 1
        )
        page = (await db.execute(page_stmt)).scalar_one_or_none()
        w = page.width_px if page and page.width_px else 2550
        est = estimate_cost(w, page.height_px if page and page.height_px else 3300)

        job = TakeoffJob(
            plan_id=plan_id,
            org_id=org_id,
            project_id=project_id,
            created_by=current_user.id,
            status="pending",
            estimated_cost_usd=Decimal(str(est["estimated_cost_usd"])),
            total_sections=est["sections"],
        )
        db.add(job)
        await db.flush()

        # Dispatch Celery task
        from app.tasks.ai_tasks import run_takeoff_analysis
        result = run_takeoff_analysis.apply_async(
            kwargs={
                "job_id": str(job.id),
                "plan_id": str(plan_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "page": 1,
            },
        )
        job.celery_task_id = result.id
        await db.commit()
        await db.refresh(job)

        return TakeoffInitResponse(
            job_id=job.id,
            plan_id=plan_id,
            status="pending",
            estimated_cost_usd=float(job.estimated_cost_usd),
            message=f"Takeoff queued. Estimated cost: ${est['estimated_cost_usd']:.4f}",
        )

    @staticmethod
    async def get_job(
        db: AsyncSession,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
        include_items: bool = False,
    ) -> TakeoffJobResponse | TakeoffJobDetailResponse:
        opts = [selectinload(TakeoffJob.items)] if include_items else []
        stmt = (
            select(TakeoffJob)
            .options(*opts)
            .where(TakeoffJob.id == job_id, TakeoffJob.org_id == org_id,
                   TakeoffJob.deleted_at.is_(None))
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Takeoff job not found")

        if include_items:
            return TakeoffJobDetailResponse(
                **{c.key: getattr(job, c.key) for c in TakeoffJob.__table__.columns
                   if hasattr(job, c.key)},
                progress_pct=job.progress_pct,
                items=[TakeoffItemResponse.model_validate(i) for i in job.items],
            )
        return TakeoffJobResponse(
            **{c.key: getattr(job, c.key) for c in TakeoffJob.__table__.columns
               if hasattr(job, c.key)},
            progress_pct=job.progress_pct,
        )

    @staticmethod
    async def update_item(
        db: AsyncSession,
        job_id: uuid.UUID,
        item_id: uuid.UUID,
        org_id: uuid.UUID,
        data: TakeoffItemUpdate,
    ) -> TakeoffItemResponse:
        stmt = (
            select(TakeoffItem)
            .join(TakeoffJob, TakeoffItem.takeoff_job_id == TakeoffJob.id)
            .where(TakeoffItem.id == item_id, TakeoffJob.id == job_id,
                   TakeoffJob.org_id == org_id)
        )
        item = (await db.execute(stmt)).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Verify job is still editable
        job_stmt = select(TakeoffJob).where(TakeoffJob.id == job_id)
        job = (await db.execute(job_stmt)).scalar_one_or_none()
        if job and not job.is_editable:
            raise HTTPException(status_code=409, detail="Takeoff is approved — no edits allowed")

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value)

        item.human_corrected = True

        if item.quantity and item.unit_cost_usd:
            item.total_cost_usd = item.quantity * item.unit_cost_usd

        await db.commit()
        await db.refresh(item)
        return TakeoffItemResponse.model_validate(item)

    @staticmethod
    async def add_item(
        db: AsyncSession,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
        data: TakeoffItemCreate,
    ) -> TakeoffItemResponse:
        job_stmt = select(TakeoffJob).where(
            TakeoffJob.id == job_id, TakeoffJob.org_id == org_id,
            TakeoffJob.deleted_at.is_(None)
        )
        job = (await db.execute(job_stmt)).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Takeoff job not found")
        if not job.is_editable:
            raise HTTPException(status_code=409, detail="Takeoff is approved — no edits allowed")

        total = (data.quantity * data.unit_cost_usd) if data.unit_cost_usd else None
        item = TakeoffItem(
            takeoff_job_id=job_id,
            human_corrected=True,
            total_cost_usd=total,
            **data.model_dump(),
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return TakeoffItemResponse.model_validate(item)

    @staticmethod
    async def delete_item(
        db: AsyncSession,
        job_id: uuid.UUID,
        item_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> None:
        stmt = (
            select(TakeoffItem)
            .join(TakeoffJob, TakeoffItem.takeoff_job_id == TakeoffJob.id)
            .where(TakeoffItem.id == item_id, TakeoffJob.id == job_id,
                   TakeoffJob.org_id == org_id)
        )
        item = (await db.execute(stmt)).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        job_stmt = select(TakeoffJob).where(TakeoffJob.id == job_id)
        job = (await db.execute(job_stmt)).scalar_one_or_none()
        if job and not job.is_editable:
            raise HTTPException(status_code=409, detail="Takeoff is approved — no edits allowed")

        await db.delete(item)
        await db.commit()

    @staticmethod
    async def approve(
        db: AsyncSession,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> TakeoffJobResponse:
        from datetime import datetime, timezone
        stmt = select(TakeoffJob).where(
            TakeoffJob.id == job_id, TakeoffJob.org_id == org_id,
            TakeoffJob.deleted_at.is_(None)
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Takeoff job not found")
        if job.status != "completed":
            raise HTTPException(status_code=422, detail="Only completed takeoffs can be approved")

        job.status = "approved"
        job.approved_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(job)

        return TakeoffJobResponse(
            **{c.key: getattr(job, c.key) for c in TakeoffJob.__table__.columns
               if hasattr(job, c.key)},
            progress_pct=job.progress_pct,
        )

    @staticmethod
    async def get_summary(
        db: AsyncSession,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> TakeoffSummaryResponse:
        stmt = (
            select(TakeoffJob)
            .options(selectinload(TakeoffJob.items))
            .where(TakeoffJob.id == job_id, TakeoffJob.org_id == org_id,
                   TakeoffJob.deleted_at.is_(None))
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Takeoff job not found")

        systems: dict[str, dict] = {}
        for item in job.items:
            s = item.system or "other"
            if s not in systems:
                systems[s] = {"count": 0, "cost": Decimal("0")}
            systems[s]["count"] += 1
            if item.total_cost_usd:
                systems[s]["cost"] += item.total_cost_usd

        breakdown = [
            CostBreakdown(system=s, item_count=v["count"], total_cost_usd=v["cost"])
            for s, v in sorted(systems.items())
        ]

        return TakeoffSummaryResponse(
            job_id=job.id,
            total_items=len(job.items),
            total_material_cost_usd=job.total_material_cost_usd or Decimal("0"),
            breakdown_by_system=breakdown,
            low_confidence_items=sum(1 for i in job.items if i.requires_review),
            requires_review_items=sum(1 for i in job.items if i.requires_review),
            human_corrected_items=sum(1 for i in job.items if i.human_corrected),
        )

    @staticmethod
    async def export_excel(
        db: AsyncSession,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> tuple[bytes, str]:
        from sqlalchemy.orm import selectinload as sl
        stmt = (
            select(TakeoffJob)
            .options(sl(TakeoffJob.items).selectinload(TakeoffItem.catalog_item))
            .where(TakeoffJob.id == job_id, TakeoffJob.org_id == org_id,
                   TakeoffJob.deleted_at.is_(None))
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Takeoff job not found")
        if job.status not in ("completed", "approved"):
            raise HTTPException(status_code=422, detail="Takeoff must be completed to export")

        from sqlalchemy.orm import selectinload as sl2
        org_stmt = select(TakeoffJob).where(TakeoffJob.id == job_id)
        from app.models.auth import Organization
        org_detail = (await db.execute(
            select(Organization).where(Organization.id == org_id)
        )).scalar_one_or_none()
        org_name = org_detail.name if org_detail else "Conduit"

        from app.modules.takeoff.exporters import export_excel as _excel
        data = _excel(job, job.items, org_name)
        filename = f"takeoff_{job_id}_{job.status}.xlsx"
        return data, filename

    @staticmethod
    async def export_pdf(
        db: AsyncSession,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
        approver_name: str | None = None,
    ) -> tuple[bytes, str]:
        from sqlalchemy.orm import selectinload as sl
        stmt = (
            select(TakeoffJob)
            .options(sl(TakeoffJob.items))
            .where(TakeoffJob.id == job_id, TakeoffJob.org_id == org_id,
                   TakeoffJob.deleted_at.is_(None))
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Takeoff job not found")
        if job.status not in ("completed", "approved"):
            raise HTTPException(status_code=422, detail="Takeoff must be completed to export")

        from app.models.auth import Organization
        org_detail = (await db.execute(
            select(Organization).where(Organization.id == org_id)
        )).scalar_one_or_none()
        org_name = org_detail.name if org_detail else "Conduit"

        from app.modules.takeoff.exporters import export_pdf as _pdf
        data = _pdf(job, job.items, org_name, approver_name)
        filename = f"takeoff_{job_id}.pdf"
        return data, filename
