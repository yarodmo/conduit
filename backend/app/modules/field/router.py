"""
Conduit Backend — Field Coordination Router (M6)

Work Zones:
  POST   /projects/{project_id}/zones                          → create zone
  GET    /projects/{project_id}/zones                          → list zones
  GET    /projects/{project_id}/zones/{zone_id}                → zone detail
  PATCH  /projects/{project_id}/zones/{zone_id}/status         → transition status

Progress Reports:
  POST   /projects/{project_id}/zones/{zone_id}/reports        → add report
  GET    /projects/{project_id}/zones/{zone_id}/reports        → list reports

Field Dashboard:
  GET    /projects/{project_id}/field-dashboard                → adaptive dashboard

Offline Sync:
  POST   /projects/{project_id}/sync/push                      → batch push from device
  GET    /projects/{project_id}/sync/pull                      → fetch updates since timestamp

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.field.schemas import (
    FieldDashboardResponse,
    ProgressReportCreate,
    ProgressReportResponse,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
    WorkZoneCreate,
    WorkZoneListItem,
    WorkZoneResponse,
    ZoneStatusUpdate,
)
from app.modules.field.service import SyncService, WorkZoneService
from app.models.projects import ProjectComplexity

router = APIRouter(tags=["Field Coordination"])


# ── Work Zones ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/zones", response_model=WorkZoneResponse, status_code=201)
async def create_zone(
    project_id: uuid.UUID,
    data: WorkZoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> WorkZoneResponse:
    return await WorkZoneService.create(db, project_id, org.id, current_user, data)


@router.get("/projects/{project_id}/zones", response_model=list[WorkZoneListItem])
async def list_zones(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[WorkZoneListItem]:
    return await WorkZoneService.list_by_project(db, project_id, org.id)


@router.get("/projects/{project_id}/zones/{zone_id}", response_model=WorkZoneResponse)
async def get_zone(
    project_id: uuid.UUID,
    zone_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> WorkZoneResponse:
    return await WorkZoneService.get(db, zone_id, org.id)


@router.patch("/projects/{project_id}/zones/{zone_id}/status", response_model=WorkZoneResponse)
async def update_zone_status(
    project_id: uuid.UUID,
    zone_id: uuid.UUID,
    data: ZoneStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> WorkZoneResponse:
    return await WorkZoneService.update_status(
        db, zone_id, org.id, project_id, current_user, data
    )


# ── Progress Reports ───────────────────────────────────────────────────────

@router.post("/projects/{project_id}/zones/{zone_id}/reports",
             response_model=ProgressReportResponse, status_code=201)
async def add_report(
    project_id: uuid.UUID,
    zone_id: uuid.UUID,
    data: ProgressReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ProgressReportResponse:
    from sqlalchemy import select
    from app.models.projects import Project

    stmt = select(Project).where(Project.id == project_id, Project.org_id == org.id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    complexity = project.complexity if project else ProjectComplexity.SIMPLE

    return await WorkZoneService.add_report(db, zone_id, org.id, current_user, data, complexity)


@router.get("/projects/{project_id}/zones/{zone_id}/reports",
            response_model=list[ProgressReportResponse])
async def list_reports(
    project_id: uuid.UUID,
    zone_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[ProgressReportResponse]:
    return await WorkZoneService.list_reports(db, zone_id, org.id)


# ── Field Dashboard ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/field-dashboard", response_model=FieldDashboardResponse)
async def get_field_dashboard(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> FieldDashboardResponse:
    return await WorkZoneService.get_field_dashboard(db, project_id, org.id)


# ── Offline Sync ───────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/sync/push", response_model=SyncPushResponse)
async def sync_push(
    project_id: uuid.UUID,
    data: SyncPushRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SyncPushResponse:
    return await SyncService.push(db, org.id, project_id, current_user, data)


@router.get("/projects/{project_id}/sync/pull", response_model=SyncPullResponse)
async def sync_pull(
    project_id: uuid.UUID,
    since: datetime = Query(..., description="ISO timestamp — fetch all changes after this point"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SyncPullResponse:
    return await SyncService.pull(db, org.id, project_id, since)
