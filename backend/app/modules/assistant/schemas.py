"""Conduit Backend — AI Assistant Schemas (M10). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    message: str = Field(min_length=3, max_length=4000)
    context_type: str = "general"
    project_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    takeoff_job_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None  # continue existing thread


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tokens_used: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    context_type: str
    title: str
    project_id: uuid.UUID | None
    message_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class AskResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageResponse
    from_cache: bool = False


class CacheGenerateRequest(BaseModel):
    project_id: uuid.UUID
    context_types: list[str] = Field(
        default_factory=lambda: ["takeoff_question", "field_question", "rfi_help"]
    )


class CacheGenerateResponse(BaseModel):
    project_id: uuid.UUID
    cached_count: int
    context_types: list[str]
