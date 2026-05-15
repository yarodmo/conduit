"""Conduit Backend — Security Monitor Schemas (M14). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SecurityEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    severity: str
    ip_address: str
    endpoint: str
    method: str
    details: dict[str, Any] | None
    resolved: bool
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SecurityStatsResponse(BaseModel):
    period_days: int
    total_events: int
    critical_events: int
    high_events: int
    unresolved_critical: int
    by_type: dict[str, int]
    top_ips: list[dict[str, Any]]


class SecurityDigestResponse(BaseModel):
    period_days: int
    total_events: int
    new_critical: int
    new_high: int
    top_attackers: list[str]
    summary: str
