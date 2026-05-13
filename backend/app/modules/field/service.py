"""
Conduit Backend — Field Coordination Service (M6)
State machine, BLOCKED→RFI auto-creation, adaptive dashboard, offline sync.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import User
from app.models.field import WorkZone, ZoneProgressReport, ZoneStatus, ZONE_TRANSITIONS
from app.models.projects import Project, ProjectComplexity
from app.models.rfis import RFI, RFISource
from app.modules.field.schemas import (
    FieldDashboardResponse,
    ProgressReportCreate,
    ProgressReportResponse,
    SyncConflict,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
    WorkZoneCreate,
    WorkZoneListItem,
    WorkZoneResponse,
    ZoneSummary,
    ZoneStatusUpdate,
)
from app.modules.rfis.schemas import RFICreate
from app.modules.rfis.service import RFIService


# ── Helpers ────────────────────────────────────────────────────────────────

async def _get_zone(db: AsyncSession, zone_id: uuid.UUID, org_id: uuid.UUID) -> WorkZone:
    stmt = (
        select(WorkZone)
        .options(selectinload(WorkZone.reports))
        .where(WorkZone.id == zone_id, WorkZone.org_id == org_id,
               WorkZone.deleted_at.is_(None))
    )
    zone = (await db.execute(stmt)).scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Work zone not found")
    return zone


async def _get_project(db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID) -> Project:
    stmt = select(Project).where(Project.id == project_id, Project.org_id == org_id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _zone_latest_progress(zone: WorkZone) -> int:
    if zone.reports:
        return zone.reports[-1].progress_pct
    return 0


def _to_zone_response(zone: WorkZone) -> WorkZoneResponse:
    return WorkZoneResponse.model_validate(zone)


def _to_report_response(report: ZoneProgressReport) -> ProgressReportResponse:
    return ProgressReportResponse.model_validate(report)


# ── WorkZone service ───────────────────────────────────────────────────────

class WorkZoneService:

    @staticmethod
    async def create(
        db: AsyncSession,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        data: WorkZoneCreate,
    ) -> WorkZoneResponse:
        zone = WorkZone(
            project_id=project_id,
            org_id=org_id,
            created_by=current_user.id,
            name=data.name,
            description=data.description,
            systems=data.systems,
            assigned_to=data.assigned_to,
            geofence=data.geofence,
            order_index=data.order_index,
        )
        db.add(zone)
        await db.commit()
        await db.refresh(zone)
        return _to_zone_response(zone)

    @staticmethod
    async def list_by_project(
        db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID
    ) -> list[WorkZoneListItem]:
        stmt = (
            select(WorkZone)
            .where(WorkZone.project_id == project_id, WorkZone.org_id == org_id,
                   WorkZone.deleted_at.is_(None))
            .order_by(WorkZone.order_index, WorkZone.created_at)
        )
        zones = (await db.execute(stmt)).scalars().all()
        return [WorkZoneListItem.model_validate(z) for z in zones]

    @staticmethod
    async def get(
        db: AsyncSession, zone_id: uuid.UUID, org_id: uuid.UUID
    ) -> WorkZoneResponse:
        zone = await _get_zone(db, zone_id, org_id)
        return _to_zone_response(zone)

    @staticmethod
    async def update_status(
        db: AsyncSession,
        zone_id: uuid.UUID,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        current_user: User,
        data: ZoneStatusUpdate,
    ) -> WorkZoneResponse:
        try:
            new_status = ZoneStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid zone status: {data.status}")

        zone = await _get_zone(db, zone_id, org_id)

        if not zone.can_transition_to(new_status):
            raise HTTPException(
                status_code=422,
                detail=f"Cannot transition from {zone.status} to {new_status.value}",
            )

        zone.status = new_status.value
        zone.updated_at = datetime.now(tz=timezone.utc)

        # BLOCKED → auto-create RFI (source=FIELD_BLOCKED, urgency=HIGH)
        if new_status == ZoneStatus.BLOCKED:
            if not data.blocked_reason:
                raise HTTPException(status_code=422, detail="blocked_reason required when status is BLOCKED")

            zone.blocked_reason = data.blocked_reason

            rfi_data = RFICreate(
                title=f"[FIELD BLOCKED] {zone.name}",
                description=(
                    f"Work zone '{zone.name}' is blocked.\n\n"
                    f"Reason: {data.blocked_reason}"
                ),
                urgency="HIGH",
            )
            rfi_response = await RFIService.create(
                db, project_id, org_id, current_user, rfi_data, RFISource.FIELD_BLOCKED
            )
            zone.blocked_rfi_id = rfi_response.id
        elif new_status == ZoneStatus.IN_PROGRESS:
            # Unblocking — clear blocked fields
            zone.blocked_reason = None
            zone.blocked_rfi_id = None

        await db.commit()
        zone = await _get_zone(db, zone_id, org_id)
        return _to_zone_response(zone)

    @staticmethod
    async def add_report(
        db: AsyncSession,
        zone_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        data: ProgressReportCreate,
        project_complexity: ProjectComplexity,
    ) -> ProgressReportResponse:
        zone = await _get_zone(db, zone_id, org_id)

        # Geofencing: validate GPS for STANDARD/COMPLEX projects
        if project_complexity != ProjectComplexity.SIMPLE:
            if zone.geofence and (data.gps_lat is not None and data.gps_lng is not None):
                if not _point_in_geofence(float(data.gps_lat), float(data.gps_lng), zone.geofence):
                    raise HTTPException(
                        status_code=422,
                        detail="GPS coordinates outside zone geofence boundary",
                    )

        materials_raw = None
        if data.materials_used:
            materials_raw = [
                {"catalog_item_id": str(m.catalog_item_id), "qty": m.qty}
                for m in data.materials_used
            ]

        report = ZoneProgressReport(
            zone_id=zone_id,
            org_id=org_id,
            reported_by=current_user.id,
            progress_pct=data.progress_pct,
            status=data.status,
            notes=data.notes,
            materials_used=materials_raw,
            gps_lat=data.gps_lat,
            gps_lng=data.gps_lng,
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return _to_report_response(report)

    @staticmethod
    async def list_reports(
        db: AsyncSession, zone_id: uuid.UUID, org_id: uuid.UUID
    ) -> list[ProgressReportResponse]:
        stmt = (
            select(ZoneProgressReport)
            .where(ZoneProgressReport.zone_id == zone_id, ZoneProgressReport.org_id == org_id)
            .order_by(ZoneProgressReport.created_at.desc())
        )
        reports = (await db.execute(stmt)).scalars().all()
        return [_to_report_response(r) for r in reports]

    @staticmethod
    async def get_field_dashboard(
        db: AsyncSession,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> FieldDashboardResponse:
        project = await _get_project(db, project_id, org_id)
        geofencing_active = project.complexity != ProjectComplexity.SIMPLE

        stmt = (
            select(WorkZone)
            .options(selectinload(WorkZone.reports))
            .where(WorkZone.project_id == project_id, WorkZone.org_id == org_id,
                   WorkZone.deleted_at.is_(None))
        )
        zones = (await db.execute(stmt)).scalars().all()

        counts: dict[str, int] = {
            "NOT_STARTED": 0, "IN_PROGRESS": 0, "COMPLETED": 0, "BLOCKED": 0,
        }
        for z in zones:
            counts[z.status] = counts.get(z.status, 0) + 1

        total = len(zones)
        completion_pct = (counts["COMPLETED"] / total * 100) if total > 0 else 0.0

        blocked_summaries = [
            ZoneSummary(
                id=z.id,
                name=z.name,
                status=z.status,
                progress_pct=_zone_latest_progress(z),
                blocked_reason=z.blocked_reason,
                blocked_rfi_id=z.blocked_rfi_id,
            )
            for z in zones if z.status == "BLOCKED"
        ]

        # Recent reports across all zones (last 10)
        report_stmt = (
            select(ZoneProgressReport)
            .where(ZoneProgressReport.org_id == org_id,
                   ZoneProgressReport.zone_id.in_([z.id for z in zones]))
            .order_by(ZoneProgressReport.created_at.desc())
            .limit(10)
        )
        recent_reports = (await db.execute(report_stmt)).scalars().all()

        return FieldDashboardResponse(
            project_id=project_id,
            total_zones=total,
            completed=counts["COMPLETED"],
            in_progress=counts["IN_PROGRESS"],
            blocked=counts["BLOCKED"],
            not_started=counts["NOT_STARTED"],
            completion_pct=round(completion_pct, 1),
            blocked_zones=blocked_summaries,
            recent_reports=[_to_report_response(r) for r in recent_reports],
            geofencing_active=geofencing_active,
        )


# ── Sync service ───────────────────────────────────────────────────────────

class SyncService:

    @staticmethod
    async def push(
        db: AsyncSession,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        current_user: User,
        data: SyncPushRequest,
    ) -> SyncPushResponse:
        conflicts: list[SyncConflict] = []
        accepted_zones = 0
        accepted_reports = 0
        server_time = datetime.now(tz=timezone.utc)

        # Process zone status updates (conflict resolution: server wins on COMPLETED)
        for update in data.zone_updates:
            try:
                zone = await _get_zone(db, update.zone_id, org_id)
            except HTTPException:
                continue

            try:
                new_status = ZoneStatus(update.status)
            except ValueError:
                continue

            if zone.status == ZoneStatus.COMPLETED.value and new_status != ZoneStatus.COMPLETED:
                # Completed zones cannot be rolled back
                conflicts.append(SyncConflict(
                    zone_id=update.zone_id,
                    conflict_reason="Server zone is COMPLETED — cannot revert",
                    server_status=zone.status,
                    client_status=update.status,
                ))
                continue

            if zone.can_transition_to(new_status):
                zone.status = new_status.value
                zone.updated_at = server_time
                accepted_zones += 1
            else:
                conflicts.append(SyncConflict(
                    zone_id=update.zone_id,
                    conflict_reason=f"Invalid transition {zone.status} → {update.status}",
                    server_status=zone.status,
                    client_status=update.status,
                ))

        # Process new progress reports
        for report_data in data.new_reports:
            try:
                await _get_zone(db, report_data.zone_id, org_id)
            except HTTPException:
                continue

            materials_raw = None
            if report_data.materials_used:
                materials_raw = [
                    {"catalog_item_id": str(m.catalog_item_id), "qty": m.qty}
                    for m in report_data.materials_used
                ]

            report = ZoneProgressReport(
                zone_id=report_data.zone_id,
                org_id=org_id,
                reported_by=current_user.id,
                progress_pct=report_data.progress_pct,
                status=report_data.status,
                notes=report_data.notes,
                materials_used=materials_raw,
                gps_lat=report_data.gps_lat,
                gps_lng=report_data.gps_lng,
            )
            db.add(report)
            accepted_reports += 1

        await db.commit()

        return SyncPushResponse(
            accepted_zone_updates=accepted_zones,
            accepted_reports=accepted_reports,
            conflicts=conflicts,
            server_time=server_time,
        )

    @staticmethod
    async def pull(
        db: AsyncSession,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        since: datetime,
    ) -> SyncPullResponse:
        server_time = datetime.now(tz=timezone.utc)

        zone_stmt = (
            select(WorkZone)
            .where(WorkZone.project_id == project_id, WorkZone.org_id == org_id,
                   WorkZone.deleted_at.is_(None), WorkZone.updated_at >= since)
            .order_by(WorkZone.order_index, WorkZone.created_at)
        )
        zones = (await db.execute(zone_stmt)).scalars().all()
        zone_ids = [z.id for z in zones]

        report_stmt = (
            select(ZoneProgressReport)
            .where(ZoneProgressReport.org_id == org_id,
                   ZoneProgressReport.created_at >= since)
        )
        if zone_ids:
            report_stmt = report_stmt.where(ZoneProgressReport.zone_id.in_(zone_ids))
        reports = (await db.execute(report_stmt)).scalars().all()

        return SyncPullResponse(
            zones=[WorkZoneListItem.model_validate(z) for z in zones],
            reports=[_to_report_response(r) for r in reports],
            since=since,
            server_time=server_time,
        )


# ── Geofencing helper ──────────────────────────────────────────────────────

def _point_in_geofence(lat: float, lng: float, geofence: dict) -> bool:
    """Ray-casting polygon test. geofence = {"coordinates": [[lng, lat], ...]}"""
    coords = geofence.get("coordinates", [])
    if not coords or len(coords) < 3:
        return True  # No valid polygon = geofence disabled

    # Treat the coords as [lng, lat] pairs (GeoJSON convention)
    inside = False
    n = len(coords)
    j = n - 1
    for i in range(n):
        xi, yi = coords[i][0], coords[i][1]
        xj, yj = coords[j][0], coords[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside
