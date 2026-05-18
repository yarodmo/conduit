"""
Conduit Backend — Takeoff Router (M5 AI Takeoff Engine)

Endpoints:
  GET  /plans/{plan_id}/takeoff/cost-preview          → cost estimate (no job created)
  POST /plans/{plan_id}/takeoff                       → initiate + dispatch Celery
  GET  /takeoff/{job_id}                              → job status + progress
  GET  /takeoff/{job_id}/items                        → all items with confidence scores
  PATCH /takeoff/{job_id}/items/{item_id}             → human correction
  POST  /takeoff/{job_id}/items                       → add missed item
  DELETE /takeoff/{job_id}/items/{item_id}            → remove false positive
  POST  /takeoff/{job_id}/approve                     → lock for editing
  GET  /takeoff/{job_id}/summary                      → cost breakdown by system
  GET  /takeoff/{job_id}/export/excel                 → Excel download
  GET  /takeoff/{job_id}/export/pdf                   → PDF download

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.takeoff.schemas import (
    CostPreviewResponse,
    TakeoffCompareResponse,
    TakeoffInitResponse,
    TakeoffItemCreate,
    TakeoffItemResponse,
    TakeoffItemUpdate,
    TakeoffJobDetailResponse,
    TakeoffJobResponse,
    TakeoffSummaryResponse,
)
from app.modules.takeoff.service import TakeoffService

router = APIRouter(tags=["AI Takeoff"])


@router.get("/plans/{plan_id}/takeoff/cost-preview", response_model=CostPreviewResponse)
async def cost_preview(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CostPreviewResponse:
    """Show estimated Claude API cost before initiating takeoff. No charge."""
    return await TakeoffService.cost_preview(db, plan_id, org.id)


@router.post("/plans/{plan_id}/takeoff", response_model=TakeoffInitResponse, status_code=202)
async def initiate_takeoff(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TakeoffInitResponse:
    """
    Initiate AI takeoff. Dispatches Celery pipeline.
    Check cost-preview first — API charge occurs on execution.
    """
    from sqlalchemy import select
    from app.models.plans import Plan
    plan_stmt = select(Plan).where(Plan.id == plan_id)
    plan = (await db.execute(plan_stmt)).scalar_one_or_none()
    project_id = plan.project_id if plan else plan_id  # fallback

    return await TakeoffService.initiate(db, plan_id, org.id, project_id, current_user)


@router.get("/takeoff/{job_id}", response_model=TakeoffJobResponse)
async def get_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TakeoffJobResponse:
    """Get takeoff job status and progress."""
    return await TakeoffService.get_job(db, job_id, org.id, include_items=False)


@router.get("/takeoff/{job_id}/items", response_model=TakeoffJobDetailResponse)
async def get_job_items(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TakeoffJobDetailResponse:
    """Get all takeoff items with confidence scores. Anti-PlanSwift: edit in same view."""
    return await TakeoffService.get_job(db, job_id, org.id, include_items=True)


@router.patch("/takeoff/{job_id}/items/{item_id}", response_model=TakeoffItemResponse)
async def update_item(
    job_id: uuid.UUID,
    item_id: uuid.UUID,
    data: TakeoffItemUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TakeoffItemResponse:
    """Correct an AI-detected item. Sets human_corrected=True for accuracy tracking."""
    return await TakeoffService.update_item(db, job_id, item_id, org.id, data)


@router.post("/takeoff/{job_id}/items", response_model=TakeoffItemResponse, status_code=201)
async def add_item(
    job_id: uuid.UUID,
    data: TakeoffItemCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TakeoffItemResponse:
    """Add a component missed by AI. Marked as human_corrected."""
    return await TakeoffService.add_item(db, job_id, org.id, data)


@router.delete("/takeoff/{job_id}/items/{item_id}", status_code=204)
async def delete_item(
    job_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> None:
    """Remove a false positive detected by AI."""
    await TakeoffService.delete_item(db, job_id, item_id, org.id)


@router.post("/takeoff/{job_id}/approve", response_model=TakeoffJobResponse)
async def approve_takeoff(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TakeoffJobResponse:
    """
    Approve and lock the takeoff. Blocks all future edits.
    Use after human review is complete.
    """
    return await TakeoffService.approve(db, job_id, org.id)


@router.get(
    "/takeoff/{job_a_id}/compare/{job_b_id}",
    response_model=TakeoffCompareResponse,
)
async def compare_takeoffs(
    job_a_id: uuid.UUID,
    job_b_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TakeoffCompareResponse:
    """
    Compare two takeoff jobs — returns cost_delta and item delta.

    Competitive claim vs Bluebeam: quantifies budget impact of plan revisions.
    cost_delta_usd > 0 means job_b costs more (scope added).
    """
    return await TakeoffService.compare(db, job_a_id, job_b_id, org.id)


@router.get("/takeoff/{job_id}/summary", response_model=TakeoffSummaryResponse)
async def get_summary(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TakeoffSummaryResponse:
    """Cost breakdown by MEP system."""
    return await TakeoffService.get_summary(db, job_id, org.id)


@router.get("/takeoff/{job_id}/export/excel")
async def export_excel(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """
    Export takeoff as Excel.
    Sheet 1: Items by system with subtotals.
    Sheet 2: Supplier Contacts (SUPERA a PlanSwift).
    """
    data, filename = await TakeoffService.export_excel(db, job_id, org.id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/takeoff/{job_id}/export/pdf")
async def export_pdf(
    job_id: uuid.UUID,
    approver: str | None = Query(None, description="Name of approving engineer"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """
    Export takeoff as PDF with org branding, summary, and approver signature.
    """
    data, filename = await TakeoffService.export_pdf(db, job_id, org.id, approver)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
