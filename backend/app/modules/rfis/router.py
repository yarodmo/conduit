"""
Conduit Backend — RFI & Markup Router (M7)

Markups:
  POST   /plans/{plan_id}/markups                           → create markup
  GET    /plans/{plan_id}/markups                           → list with RFI links
  POST   /plans/{plan_id}/markups/{markup_id}/escalate-rfi → CLOUD → RFI (1 click)

RFIs:
  POST   /projects/{project_id}/rfis                        → create manual RFI
  GET    /projects/{project_id}/rfis                        → list (filtrable por status)
  GET    /rfis/{rfi_id}                                     → detail + comments
  POST   /rfis/{rfi_id}/submit                              → DRAFT → SUBMITTED
  POST   /rfis/{rfi_id}/assign                              → SUBMITTED → UNDER_REVIEW
  POST   /rfis/{rfi_id}/answer                              → UNDER_REVIEW → ANSWERED
  POST   /rfis/{rfi_id}/close                               → ANSWERED → CLOSED
  POST   /rfis/{rfi_id}/reject                              → ANSWERED → REJECTED (loop)
  POST   /rfis/{rfi_id}/comments                            → add comment (any status)
  GET    /rfis/{rfi_id}/export/pdf                          → legal document PDF

Change Orders:
  POST   /rfis/{rfi_id}/change-order                        → create (only CLOSED RFI)
  POST   /change-orders/{co_id}/approve                     → PENDING → APPROVED + PDF
  POST   /change-orders/{co_id}/reject                      → PENDING → REJECTED

Bliss Systems LLC — APEX Standard
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.rfis.schemas import (
    ChangeOrderCreate, ChangeOrderResponse,
    MarkupCreate, MarkupResponse,
    RFIAnswer, RFIAssign, RFICommentCreate, RFICommentResponse,
    RFICreate, RFIListItem, RFIRejectRequest, RFIResponse,
)
from app.modules.rfis.service import ChangeOrderService, MarkupService, RFIService

router = APIRouter(tags=["RFIs & Markups"])


# ── Markups ────────────────────────────────────────────────────────────────

@router.post("/plans/{plan_id}/markups", response_model=MarkupResponse, status_code=201)
async def create_markup(
    plan_id: uuid.UUID,
    data: MarkupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> MarkupResponse:
    return await MarkupService.create(db, plan_id, org.id, current_user, data)


@router.get("/plans/{plan_id}/markups", response_model=list[MarkupResponse])
async def list_markups(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[MarkupResponse]:
    return await MarkupService.list_by_plan(db, plan_id, org.id)


@router.post("/plans/{plan_id}/markups/{markup_id}/escalate-rfi",
             response_model=RFIResponse, status_code=201)
async def escalate_to_rfi(
    plan_id: uuid.UUID,
    markup_id: uuid.UUID,
    title: Annotated[str, Query(min_length=5)],
    description: Annotated[str, Query(min_length=10)],
    project_id: uuid.UUID = Query(...),
    urgency: str = Query("MEDIUM"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFIResponse:
    """Anti-Bluebeam: CLOUD markup → RFI in one click."""
    return await RFIService.escalate_markup(
        db, markup_id, org.id, project_id, current_user, title, description, urgency
    )


# ── RFIs ───────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/rfis", response_model=RFIResponse, status_code=201)
async def create_rfi(
    project_id: uuid.UUID,
    data: RFICreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFIResponse:
    return await RFIService.create(db, project_id, org.id, current_user, data)


@router.get("/projects/{project_id}/rfis", response_model=list[RFIListItem])
async def list_rfis(
    project_id: uuid.UUID,
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[RFIListItem]:
    return await RFIService.list_by_project(db, project_id, org.id, status)


@router.get("/rfis/{rfi_id}", response_model=RFIResponse)
async def get_rfi(
    rfi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFIResponse:
    return await RFIService.get(db, rfi_id, org.id)


@router.post("/rfis/{rfi_id}/submit", response_model=RFIResponse)
async def submit_rfi(
    rfi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFIResponse:
    return await RFIService.submit(db, rfi_id, org.id)


@router.post("/rfis/{rfi_id}/assign", response_model=RFIResponse)
async def assign_rfi(
    rfi_id: uuid.UUID,
    data: RFIAssign,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFIResponse:
    return await RFIService.assign(db, rfi_id, org.id, data)


@router.post("/rfis/{rfi_id}/answer", response_model=RFIResponse)
async def answer_rfi(
    rfi_id: uuid.UUID,
    data: RFIAnswer,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFIResponse:
    return await RFIService.answer(db, rfi_id, org.id, current_user, data)


@router.post("/rfis/{rfi_id}/close", response_model=RFIResponse)
async def close_rfi(
    rfi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFIResponse:
    return await RFIService.close(db, rfi_id, org.id)


@router.post("/rfis/{rfi_id}/reject", response_model=RFIResponse)
async def reject_rfi(
    rfi_id: uuid.UUID,
    data: RFIRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFIResponse:
    return await RFIService.reject(db, rfi_id, org.id, current_user, data)


@router.post("/rfis/{rfi_id}/comments", response_model=RFICommentResponse, status_code=201)
async def add_comment(
    rfi_id: uuid.UUID,
    data: RFICommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> RFICommentResponse:
    return await RFIService.add_comment(db, rfi_id, org.id, current_user, data)


@router.get("/rfis/{rfi_id}/export/pdf")
async def export_rfi_pdf(
    rfi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """Legal document PDF with org header, full timeline, Change Order summary."""
    data, filename = await ChangeOrderService.export_pdf(db, rfi_id, org.id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Change Orders ──────────────────────────────────────────────────────────

@router.post("/rfis/{rfi_id}/change-order", response_model=ChangeOrderResponse, status_code=201)
async def create_change_order(
    rfi_id: uuid.UUID,
    data: ChangeOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ChangeOrderResponse:
    """Create Change Order from CLOSED RFI. Only one CO per RFI allowed."""
    return await ChangeOrderService.create(db, rfi_id, org.id, current_user, data)


@router.post("/change-orders/{co_id}/approve", response_model=ChangeOrderResponse)
async def approve_co(
    co_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ChangeOrderResponse:
    return await ChangeOrderService.approve(db, co_id, org.id, current_user)


@router.post("/change-orders/{co_id}/reject", response_model=ChangeOrderResponse)
async def reject_co(
    co_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ChangeOrderResponse:
    return await ChangeOrderService.reject(db, co_id, org.id)
