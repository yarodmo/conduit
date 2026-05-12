"""Conduit Backend — RFI & Markup Schemas (M7). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ── Markup ─────────────────────────────────────────────────────────────────

class MarkupCreate(BaseModel):
    type: str
    coordinates: dict[str, Any]
    color: str = "#FF0000"
    label: str | None = None
    page_number: int = 1


class MarkupResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    type: str
    coordinates: dict[str, Any]
    color: str
    label: str | None
    page_number: int
    resolved: bool
    rfi_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── RFI ───────────────────────────────────────────────────────────────────

class RFICreate(BaseModel):
    title: str = Field(min_length=5, max_length=512)
    description: str = Field(min_length=10)
    urgency: str = "MEDIUM"
    due_date: datetime | None = None
    assigned_to: uuid.UUID | None = None
    markup_id: uuid.UUID | None = None


class RFIAssign(BaseModel):
    assigned_to: uuid.UUID
    due_date: datetime | None = None


class RFIAnswer(BaseModel):
    response: str = Field(min_length=10)


class RFIRejectRequest(BaseModel):
    reason: str = Field(min_length=10)


class RFICommentCreate(BaseModel):
    content: str = Field(min_length=1)
    is_official_response: bool = False


class RFICommentResponse(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    content: str
    is_official_response: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RFIResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    rfi_number: str
    title: str
    description: str
    status: str
    urgency: str
    source: str
    assigned_to: uuid.UUID | None
    markup_id: uuid.UUID | None
    due_date: datetime | None
    submitted_at: datetime | None
    answered_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    comments: list[RFICommentResponse] = Field(default_factory=list)
    change_order_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class RFIListItem(BaseModel):
    id: uuid.UUID
    rfi_number: str
    title: str
    status: str
    urgency: str
    source: str
    assigned_to: uuid.UUID | None
    due_date: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Change Order ──────────────────────────────────────────────────────────

class ChangeOrderCreate(BaseModel):
    scope_change_description: str = Field(min_length=20)
    cost_impact_usd: Decimal
    time_impact_days: int = 0
    affected_systems: list[str] = Field(default_factory=list)


class ChangeOrderResponse(BaseModel):
    id: uuid.UUID
    rfi_id: uuid.UUID
    co_number: str
    scope_change_description: str
    cost_impact_usd: Decimal
    time_impact_days: int
    affected_systems: list[str] | None
    status: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
