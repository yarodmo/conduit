"""
Conduit Backend — Report Job Models (M9)
Async report generation queue.

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ConduitBase


class ReportType(str, enum.Enum):
    TAKEOFF_EXCEL      = "takeoff_excel"
    TAKEOFF_PDF        = "takeoff_pdf"
    PROJECT_PROGRESS   = "project_progress"
    RFI_PDF            = "rfi_pdf"
    CHANGE_ORDER_PDF   = "change_order_pdf"


class ReportStatus(str, enum.Enum):
    QUEUED     = "queued"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"


class ReportJob(ConduitBase):
    __tablename__ = "report_jobs"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    report_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
