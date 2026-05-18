"""Conduit Backend — Field Coordination Schemas (M6). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ── Work Zone ─────────────────────────────────────────────────────────────

class WorkZoneCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    systems: list[str] = Field(default_factory=list)
    assigned_to: uuid.UUID | None = None
    geofence: dict[str, Any] | None = None
    order_index: int = 0


class ZoneStatusUpdate(BaseModel):
    status: str
    blocked_reason: str | None = None


class WorkZoneResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    systems: list[str]
    status: str
    assigned_to: uuid.UUID | None
    geofence: dict[str, Any] | None
    order_index: int
    blocked_reason: str | None
    cached_takeoff_items: list[dict] | None = None
    blocked_rfi_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkZoneListItem(BaseModel):
    id: uuid.UUID
    name: str
    systems: list[str]
    status: str
    assigned_to: uuid.UUID | None
    order_index: int
    blocked_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Progress Report ───────────────────────────────────────────────────────

class MaterialUsed(BaseModel):
    catalog_item_id: uuid.UUID
    qty: float


class ProgressReportCreate(BaseModel):
    progress_pct: int = Field(ge=0, le=100)
    status: str
    notes: str | None = None
    materials_used: list[MaterialUsed] | None = None
    gps_lat: Decimal | None = None
    gps_lng: Decimal | None = None


class ProgressReportResponse(BaseModel):
    id: uuid.UUID
    zone_id: uuid.UUID
    reported_by: uuid.UUID
    progress_pct: int
    status: str
    notes: str | None
    materials_used: list[dict[str, Any]] | None
    gps_lat: Decimal | None
    gps_lng: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Field Dashboard ───────────────────────────────────────────────────────

class ZoneSummary(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    progress_pct: int
    blocked_reason: str | None
    blocked_rfi_id: uuid.UUID | None


class FieldDashboardResponse(BaseModel):
    project_id: uuid.UUID
    total_zones: int
    completed: int
    in_progress: int
    blocked: int
    not_started: int
    completion_pct: float
    blocked_zones: list[ZoneSummary]
    recent_reports: list[ProgressReportResponse]
    geofencing_active: bool


# ── Offline Sync ──────────────────────────────────────────────────────────

class SyncZoneUpdate(BaseModel):
    zone_id: uuid.UUID
    status: str
    client_updated_at: datetime


class SyncReportCreate(BaseModel):
    zone_id: uuid.UUID
    progress_pct: int = Field(ge=0, le=100)
    status: str
    notes: str | None = None
    materials_used: list[MaterialUsed] | None = None
    gps_lat: Decimal | None = None
    gps_lng: Decimal | None = None
    client_created_at: datetime


class SyncPushRequest(BaseModel):
    zone_updates: list[SyncZoneUpdate] = Field(default_factory=list)
    new_reports: list[SyncReportCreate] = Field(default_factory=list)


class SyncConflict(BaseModel):
    zone_id: uuid.UUID
    conflict_reason: str
    server_status: str
    client_status: str


class SyncPushResponse(BaseModel):
    accepted_zone_updates: int
    accepted_reports: int
    conflicts: list[SyncConflict]
    server_time: datetime


class SyncPullResponse(BaseModel):
    zones: list[WorkZoneListItem]
    reports: list[ProgressReportResponse]
    since: datetime
    server_time: datetime
