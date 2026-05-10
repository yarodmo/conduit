"""
Conduit Backend — Plan Schemas (M3 + M4)

Bliss Systems LLC — APEX Standard
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class PlanUploadResponse(BaseModel):
    plan_id: uuid.UUID
    job_id: uuid.UUID
    status: str
    message: str


class ProcessingJobStatus(BaseModel):
    job_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    current_step: str | None
    progress_pct: int
    error_message: str | None


class PlanPageResponse(BaseModel):
    page_number: int
    thumb_url: str
    full_url: str
    width_px: int | None
    height_px: int | None
    orientation: str | None

    model_config = {"from_attributes": True}


class PlanMetadataResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    original_filename: str
    source_type: str
    status: str
    total_pages: int | None
    plan_type: str
    scale_text: str | None
    plan_number: str | None
    plan_title: str | None
    plan_date: str | None
    plan_revision: str | None
    color_legend: dict[str, Any] | None
    complexity_score: str | None
    quality_score: int | None
    deskew_applied: bool
    pages: list[PlanPageResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PlanListItem(BaseModel):
    id: uuid.UUID
    name: str
    original_filename: str
    source_type: str
    status: str
    total_pages: int | None
    plan_type: str
    complexity_score: str | None
    thumb_url: str | None

    model_config = {"from_attributes": True}
