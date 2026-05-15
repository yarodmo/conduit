"""
Conduit Backend — Security Monitor Router (M14)

  GET    /security/events                    → list events (filters: severity, type, unresolved)
  GET    /security/stats                     → 7-day stats summary
  PATCH  /security/events/{id}/resolve       → mark event resolved
  POST   /security/events/test               → fire test event (dev/staging only)
  GET    /security/digest                    → daily digest for current user's org

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.security.schemas import (
    SecurityDigestResponse,
    SecurityEventResponse,
    SecurityStatsResponse,
)
from app.modules.security.service import SecurityService

router = APIRouter(prefix="/security", tags=["Security Monitor"])


@router.get("/events", response_model=list[SecurityEventResponse])
async def list_events(
    severity: str | None = Query(None),
    event_type: str | None = Query(None),
    unresolved_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[SecurityEventResponse]:
    return await SecurityService.list_events(
        db, org.id, severity, event_type, unresolved_only, page, page_size
    )


@router.get("/stats", response_model=SecurityStatsResponse)
async def get_stats(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SecurityStatsResponse:
    return await SecurityService.get_stats(db, org.id, days)


@router.get("/digest", response_model=SecurityDigestResponse)
async def get_digest(
    days: int = Query(1, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SecurityDigestResponse:
    return await SecurityService.generate_digest(db, org.id, days)


@router.patch("/events/{event_id}/resolve", response_model=SecurityEventResponse)
async def resolve_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    __: Organization = Depends(get_current_org),
) -> SecurityEventResponse:
    return await SecurityService.resolve_event(db, event_id)


@router.post("/events/test", response_model=SecurityEventResponse, status_code=201)
async def create_test_event(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SecurityEventResponse:
    """Create a test security event to verify alert pipeline."""
    return await SecurityService.log_event(
        db,
        event_type="test_event",
        severity="LOW",
        ip_address="127.0.0.1",
        endpoint="/security/events/test",
        method="POST",
        details={"message": "Manual test event", "triggered_by": str(current_user.id)},
        org_id=org.id,
        user_id=current_user.id,
    )
