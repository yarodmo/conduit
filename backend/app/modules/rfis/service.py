"""
Conduit Backend — RFI Service (M7)
State machine, auto-numbering, markup escalation, Change Order flow.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import User
from app.models.rfis import (
    ChangeOrder, Markup, RFI, RFIComment, RFISource, RFIStatus,
)
from app.modules.rfis.schemas import (
    ChangeOrderCreate, ChangeOrderResponse,
    MarkupCreate, MarkupResponse,
    RFIAnswer, RFIAssign, RFICommentCreate, RFICommentResponse,
    RFICreate, RFIListItem, RFIRejectRequest, RFIResponse,
)


# ── Auto-numbering ─────────────────────────────────────────────────────────

async def _next_rfi_number(db: AsyncSession, project_id: uuid.UUID) -> str:
    stmt = select(func.count()).where(RFI.project_id == project_id)
    count = (await db.execute(stmt)).scalar_one()
    return f"RFI-{str(count + 1).zfill(3)}"


async def _next_co_number(db: AsyncSession, org_id: uuid.UUID) -> str:
    stmt = select(func.count()).where(ChangeOrder.org_id == org_id)
    count = (await db.execute(stmt)).scalar_one()
    return f"CO-{str(count + 1).zfill(3)}"


# ── RFI fetch helpers ──────────────────────────────────────────────────────

async def _get_rfi(db: AsyncSession, rfi_id: uuid.UUID, org_id: uuid.UUID) -> RFI:
    stmt = (
        select(RFI)
        .options(selectinload(RFI.comments), selectinload(RFI.change_order))
        .where(RFI.id == rfi_id, RFI.org_id == org_id, RFI.deleted_at.is_(None))
    )
    rfi = (await db.execute(stmt)).scalar_one_or_none()
    if not rfi:
        raise HTTPException(status_code=404, detail="RFI not found")
    return rfi


def _to_rfi_response(rfi: RFI) -> RFIResponse:
    return RFIResponse(
        id=rfi.id,
        project_id=rfi.project_id,
        rfi_number=rfi.rfi_number,
        title=rfi.title,
        description=rfi.description,
        status=rfi.status,
        urgency=rfi.urgency,
        source=rfi.source,
        assigned_to=rfi.assigned_to,
        markup_id=rfi.markup_id,
        due_date=rfi.due_date,
        submitted_at=rfi.submitted_at,
        answered_at=rfi.answered_at,
        closed_at=rfi.closed_at,
        created_at=rfi.created_at,
        comments=[RFICommentResponse.model_validate(c) for c in rfi.comments],
        change_order_id=rfi.change_order.id if rfi.change_order else None,
    )


# ── Markup service ─────────────────────────────────────────────────────────

class MarkupService:

    @staticmethod
    async def create(
        db: AsyncSession,
        plan_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        data: MarkupCreate,
    ) -> MarkupResponse:
        markup = Markup(
            plan_id=plan_id,
            org_id=org_id,
            author_id=current_user.id,
            **data.model_dump(),
        )
        db.add(markup)
        await db.commit()
        await db.refresh(markup)
        resp = MarkupResponse.model_validate(markup)
        # Anti-Bluebeam: CLOUD markup signals RFI should be created
        if markup.type == "CLOUD":
            resp = resp.model_copy(update={})
        return resp

    @staticmethod
    async def list_by_plan(
        db: AsyncSession,
        plan_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> list[MarkupResponse]:
        stmt = (
            select(Markup)
            .options(selectinload(Markup.rfi))
            .where(Markup.plan_id == plan_id, Markup.org_id == org_id,
                   Markup.deleted_at.is_(None))
            .order_by(Markup.created_at)
        )
        markups = (await db.execute(stmt)).scalars().all()
        results = []
        for m in markups:
            r = MarkupResponse.model_validate(m)
            if m.rfi:
                r = r.model_copy(update={"rfi_id": m.rfi.id})
            results.append(r)
        return results


# ── RFI service ────────────────────────────────────────────────────────────

class RFIService:

    @staticmethod
    async def create(
        db: AsyncSession,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        data: RFICreate,
        source: RFISource = RFISource.MANUAL,
    ) -> RFIResponse:
        rfi_number = await _next_rfi_number(db, project_id)
        rfi = RFI(
            project_id=project_id,
            org_id=org_id,
            created_by=current_user.id,
            rfi_number=rfi_number,
            source=source.value,
            title=data.title,
            description=data.description,
            urgency=data.urgency,
            due_date=data.due_date,
            assigned_to=data.assigned_to,
            markup_id=data.markup_id,
        )
        db.add(rfi)

        if data.markup_id:
            markup = await db.get(Markup, data.markup_id)
            if markup:
                markup.resolved = False  # still open until RFI is closed

        await db.commit()
        await db.refresh(rfi)
        rfi = await _get_rfi(db, rfi.id, org_id)
        return _to_rfi_response(rfi)

    @staticmethod
    async def escalate_markup(
        db: AsyncSession,
        markup_id: uuid.UUID,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        current_user: User,
        title: str,
        description: str,
        urgency: str = "MEDIUM",
    ) -> RFIResponse:
        """CLOUD markup → RFI in one click. Anti-Bluebeam rule."""
        markup = await db.get(Markup, markup_id)
        if not markup or markup.org_id != org_id:
            raise HTTPException(status_code=404, detail="Markup not found")
        if markup.type != "CLOUD":
            raise HTTPException(status_code=422, detail="Only CLOUD markups can be escalated to RFI")

        existing = (await db.execute(
            select(RFI).where(RFI.markup_id == markup_id)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Markup already has an RFI")

        data = RFICreate(
            title=title, description=description, urgency=urgency, markup_id=markup_id,
        )
        return await RFIService.create(
            db, project_id, org_id, current_user, data, RFISource.MARKUP_ESCALATED
        )

    @staticmethod
    async def list_by_project(
        db: AsyncSession,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        status_filter: str | None = None,
    ) -> list[RFIListItem]:
        stmt = select(RFI).where(
            RFI.project_id == project_id,
            RFI.org_id == org_id,
            RFI.deleted_at.is_(None),
        )
        if status_filter:
            stmt = stmt.where(RFI.status == status_filter)
        rfis = (await db.execute(stmt.order_by(RFI.created_at.desc()))).scalars().all()
        return [RFIListItem.model_validate(r) for r in rfis]

    @staticmethod
    async def get(
        db: AsyncSession, rfi_id: uuid.UUID, org_id: uuid.UUID
    ) -> RFIResponse:
        return _to_rfi_response(await _get_rfi(db, rfi_id, org_id))

    @staticmethod
    async def _transition(
        db: AsyncSession,
        rfi_id: uuid.UUID,
        org_id: uuid.UUID,
        new_status: RFIStatus,
        **extra_fields: object,
    ) -> RFIResponse:
        rfi = await _get_rfi(db, rfi_id, org_id)
        if not rfi.can_transition_to(new_status):
            raise HTTPException(
                status_code=422,
                detail=f"Cannot transition from {rfi.status} to {new_status.value}",
            )
        rfi.status = new_status.value
        for k, v in extra_fields.items():
            setattr(rfi, k, v)
        await db.commit()
        return _to_rfi_response(await _get_rfi(db, rfi_id, org_id))

    @staticmethod
    async def submit(db: AsyncSession, rfi_id: uuid.UUID, org_id: uuid.UUID) -> RFIResponse:
        return await RFIService._transition(
            db, rfi_id, org_id, RFIStatus.SUBMITTED,
            submitted_at=datetime.now(tz=timezone.utc),
        )

    @staticmethod
    async def assign(
        db: AsyncSession, rfi_id: uuid.UUID, org_id: uuid.UUID, data: RFIAssign
    ) -> RFIResponse:
        return await RFIService._transition(
            db, rfi_id, org_id, RFIStatus.UNDER_REVIEW,
            assigned_to=data.assigned_to,
            due_date=data.due_date,
        )

    @staticmethod
    async def answer(
        db: AsyncSession,
        rfi_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        data: RFIAnswer,
    ) -> RFIResponse:
        await _get_rfi(db, rfi_id, org_id)  # validates ownership
        comment = RFIComment(
            rfi_id=rfi_id,
            author_id=current_user.id,
            content=data.response,
            is_official_response=True,
        )
        db.add(comment)
        return await RFIService._transition(
            db, rfi_id, org_id, RFIStatus.ANSWERED,
            answered_at=datetime.now(tz=timezone.utc),
        )

    @staticmethod
    async def close(db: AsyncSession, rfi_id: uuid.UUID, org_id: uuid.UUID) -> RFIResponse:
        rfi = await _get_rfi(db, rfi_id, org_id)
        # Resolve linked markup
        if rfi.markup_id:
            markup = await db.get(Markup, rfi.markup_id)
            if markup:
                markup.resolved = True
        return await RFIService._transition(
            db, rfi_id, org_id, RFIStatus.CLOSED,
            closed_at=datetime.now(tz=timezone.utc),
        )

    @staticmethod
    async def reject(
        db: AsyncSession,
        rfi_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        data: RFIRejectRequest,
    ) -> RFIResponse:
        await _get_rfi(db, rfi_id, org_id)  # validates ownership
        comment = RFIComment(
            rfi_id=rfi_id,
            author_id=current_user.id,
            content=f"[REJECTED] {data.reason}",
            is_official_response=True,
        )
        db.add(comment)
        return await RFIService._transition(db, rfi_id, org_id, RFIStatus.REJECTED)

    @staticmethod
    async def add_comment(
        db: AsyncSession,
        rfi_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        data: RFICommentCreate,
    ) -> RFICommentResponse:
        await _get_rfi(db, rfi_id, org_id)  # validates ownership
        comment = RFIComment(
            rfi_id=rfi_id,
            author_id=current_user.id,
            **data.model_dump(),
        )
        db.add(comment)
        await db.commit()
        await db.refresh(comment)
        return RFICommentResponse.model_validate(comment)


# ── Change Order service ───────────────────────────────────────────────────

class ChangeOrderService:

    @staticmethod
    async def create(
        db: AsyncSession,
        rfi_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        data: ChangeOrderCreate,
    ) -> ChangeOrderResponse:
        rfi = await _get_rfi(db, rfi_id, org_id)
        if rfi.status != RFIStatus.CLOSED.value:
            raise HTTPException(status_code=422, detail="RFI must be CLOSED to create a Change Order")
        # Explicit SELECT — avoids SQLAlchemy identity map returning stale relationship
        existing_co = (await db.execute(
            select(ChangeOrder).where(ChangeOrder.rfi_id == rfi_id)
        )).scalar_one_or_none()
        if existing_co:
            raise HTTPException(status_code=409, detail="Change Order already exists for this RFI")

        co_number = await _next_co_number(db, org_id)
        co = ChangeOrder(
            rfi_id=rfi_id,
            org_id=org_id,
            created_by=current_user.id,
            co_number=co_number,
            **data.model_dump(),
        )
        db.add(co)
        await db.commit()
        await db.refresh(co)
        return ChangeOrderResponse.model_validate(co)

    @staticmethod
    async def _get_co(
        db: AsyncSession, co_id: uuid.UUID, org_id: uuid.UUID
    ) -> ChangeOrder:
        stmt = select(ChangeOrder).where(
            ChangeOrder.id == co_id, ChangeOrder.org_id == org_id,
            ChangeOrder.deleted_at.is_(None),
        )
        co = (await db.execute(stmt)).scalar_one_or_none()
        if not co:
            raise HTTPException(status_code=404, detail="Change Order not found")
        return co

    @staticmethod
    async def approve(
        db: AsyncSession,
        co_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
    ) -> ChangeOrderResponse:
        co = await ChangeOrderService._get_co(db, co_id, org_id)
        if co.status != "PENDING":
            raise HTTPException(status_code=422, detail="Only PENDING Change Orders can be approved")
        co.status = "APPROVED"
        co.approved_by = current_user.id
        co.approved_at = datetime.now(tz=timezone.utc)

        # Generate PDF (stored in S3 key for later retrieval)
        co.pdf_s3_key = f"change_orders/{org_id}/{co_id}/co_{co.co_number}.pdf"

        await db.commit()
        await db.refresh(co)
        return ChangeOrderResponse.model_validate(co)

    @staticmethod
    async def reject(
        db: AsyncSession, co_id: uuid.UUID, org_id: uuid.UUID
    ) -> ChangeOrderResponse:
        co = await ChangeOrderService._get_co(db, co_id, org_id)
        if co.status != "PENDING":
            raise HTTPException(status_code=422, detail="Only PENDING Change Orders can be rejected")
        co.status = "REJECTED"
        await db.commit()
        await db.refresh(co)
        return ChangeOrderResponse.model_validate(co)

    @staticmethod
    async def export_pdf(
        db: AsyncSession,
        rfi_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> tuple[bytes, str]:
        from app.modules.rfis.exporter import export_rfi_pdf
        rfi = await _get_rfi(db, rfi_id, org_id)

        from app.models.auth import Organization
        org = (await db.execute(
            select(Organization).where(Organization.id == org_id)
        )).scalar_one_or_none()
        org_name = org.name if org else "Conduit"

        data = export_rfi_pdf(rfi, org_name)
        filename = f"RFI-{rfi.rfi_number}.pdf"
        return data, filename
