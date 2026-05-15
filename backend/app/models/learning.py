"""
Conduit Backend — Self-Learning Pipeline Models (M13)
Aggregated insights from human corrections, nightly via Celery beat.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ConduitBase


class LearningInsight(ConduitBase):
    __tablename__ = "learning_insights"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_takeoffs_analyzed: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    total_corrections: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    avg_accuracy_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    accuracy_by_version: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)
    top_error_patterns: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON(), nullable=True)
    low_accuracy_prompts: Mapped[list[str] | None] = mapped_column(JSON(), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text(), nullable=True)


class LearningCorrectionEvent(ConduitBase):
    __tablename__ = "learning_correction_events"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    takeoff_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("takeoff_jobs.id", ondelete="CASCADE"), nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    component_type: Mapped[str] = mapped_column(String(30), nullable=False)
    original_confidence: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    correction_type: Mapped[str] = mapped_column(String(20), nullable=False)
