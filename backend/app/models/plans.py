"""
Conduit Backend — Plan Models (M3 Plan Processor + M4 Plan Viewer)
Sprint 1: Upload, processing pipeline, tile server.

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ConduitBase


class PlanSourceType(str, enum.Enum):
    pdf = "pdf"
    phone_photo = "phone_photo"
    camera_direct = "camera_direct"
    scan = "scan"


class PlanType(str, enum.Enum):
    hvac = "hvac"
    electrical = "electrical"
    plumbing = "plumbing"
    mep = "mep"
    fire_protection = "fire_protection"
    unknown = "unknown"


class PlanStatus(str, enum.Enum):
    uploading = "uploading"
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Plan(ConduitBase):
    __tablename__ = "plans"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="pdf")
    s3_key_original: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    total_pages: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploading")

    # Auto-detected metadata (STEP 3 analysis)
    plan_type: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    scale_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    plan_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    plan_revision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_legend: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)
    complexity_score: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quality_score: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    deskew_applied: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    pages: Mapped[list["PlanPage"]] = relationship(
        "PlanPage", back_populates="plan", cascade="all, delete-orphan",
        order_by="PlanPage.page_number",
    )
    processing_jobs: Mapped[list["PlanProcessingJob"]] = relationship(
        "PlanProcessingJob", back_populates="plan", cascade="all, delete-orphan",
        order_by="PlanProcessingJob.created_at",
    )

    @property
    def latest_job(self) -> "PlanProcessingJob | None":
        return self.processing_jobs[-1] if self.processing_jobs else None


class PlanProcessingJob(ConduitBase):
    __tablename__ = "plan_processing_jobs"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    plan: Mapped["Plan"] = relationship("Plan", back_populates="processing_jobs")


class PlanPage(ConduitBase):
    __tablename__ = "plan_pages"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    s3_key_full: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    s3_key_thumb: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    width_px: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    orientation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    detected_text_blocks: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)

    plan: Mapped["Plan"] = relationship("Plan", back_populates="pages")
