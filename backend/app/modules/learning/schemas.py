"""Conduit Backend — Self-Learning Pipeline Schemas (M13). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class ErrorPattern(BaseModel):
    component_type: str
    correction_count: int
    avg_confidence: float
    correction_types: list[str]


class PromptAccuracy(BaseModel):
    prompt_version: str
    takeoff_count: int
    avg_accuracy_pct: float
    correction_count: int
    below_threshold: bool  # True if < 70%


class InsightResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    total_takeoffs_analyzed: int
    total_corrections: int
    avg_accuracy_pct: Decimal | None
    accuracy_by_version: dict[str, Any] | None
    top_error_patterns: list[dict[str, Any]] | None
    low_accuracy_prompts: list[str] | None
    recommendation: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LearningDashboardResponse(BaseModel):
    latest_insight: InsightResponse | None
    prompt_accuracy: list[PromptAccuracy]
    top_errors: list[ErrorPattern]
    total_corrections_all_time: int
    learning_events_last_30d: int


class TriggerAnalysisResponse(BaseModel):
    org_id: uuid.UUID
    period_analyzed_days: int
    insight_id: uuid.UUID
    summary: str
