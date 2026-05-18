"""
Conduit Backend — Takeoff Schemas (M5)

Bliss Systems LLC — APEX Standard
"""

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class CostPreviewResponse(BaseModel):
    plan_id: uuid.UUID
    sections: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    message: str


class TakeoffInitResponse(BaseModel):
    job_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    estimated_cost_usd: float | None
    message: str


class TakeoffItemResponse(BaseModel):
    id: uuid.UUID
    type: str
    tag: str | None
    quantity: Decimal
    unit: str
    specification: str
    system: str | None
    cfm_or_gpm: Decimal | None
    confidence: int
    notes: str | None
    requires_review: bool
    human_corrected: bool
    correction_notes: str | None
    unit_cost_usd: Decimal | None
    total_cost_usd: Decimal | None
    section_index: int | None

    model_config = {"from_attributes": True}


class TakeoffItemUpdate(BaseModel):
    quantity: Decimal | None = None
    unit: str | None = None
    specification: str | None = None
    system: str | None = None
    cfm_or_gpm: Decimal | None = None
    notes: str | None = None
    correction_notes: str | None = None
    unit_cost_usd: Decimal | None = None


class TakeoffItemCreate(BaseModel):
    type: str
    tag: str | None = None
    quantity: Decimal = Field(gt=0)
    unit: str = "EA"
    specification: str
    system: str | None = None
    cfm_or_gpm: Decimal | None = None
    notes: str | None = None
    unit_cost_usd: Decimal | None = None


class TakeoffJobResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    model_version: str | None
    prompt_version: str
    total_sections: int
    sections_completed: int
    progress_pct: int
    total_items: int | None
    low_confidence_count: int | None
    accuracy_score: Decimal | None
    estimated_cost_usd: Decimal | None
    actual_cost_usd: Decimal | None
    total_material_cost_usd: Decimal | None
    error_message: str | None

    model_config = {"from_attributes": True}


class TakeoffJobDetailResponse(TakeoffJobResponse):
    items: list[TakeoffItemResponse] = Field(default_factory=list)


class CostBreakdown(BaseModel):
    system: str
    item_count: int
    total_cost_usd: Decimal


class TakeoffSummaryResponse(BaseModel):
    job_id: uuid.UUID
    total_items: int
    total_material_cost_usd: Decimal
    breakdown_by_system: list[CostBreakdown]
    low_confidence_items: int
    requires_review_items: int
    human_corrected_items: int


class TakeoffCompareResponse(BaseModel):
    """
    Cost and item delta between two takeoff versions.

    Competitive claim vs Bluebeam (PROMPT 13 test #5):
      Bluebeam shows visual diff only.
      Conduit quantifies cost_delta_usd so the PM knows the budget impact.
    """
    job_a_id: uuid.UUID
    job_b_id: uuid.UUID
    cost_delta_usd: Decimal
    items_added: int
    items_removed: int
