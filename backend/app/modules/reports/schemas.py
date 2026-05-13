"""Conduit Backend — Report Job Schemas (M9). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ReportJobResponse(BaseModel):
    id: uuid.UUID
    report_type: str
    entity_id: uuid.UUID
    status: str
    download_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
