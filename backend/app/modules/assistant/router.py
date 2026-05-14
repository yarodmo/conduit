"""
Conduit Backend — AI Assistant Router (M10)
Claude-powered in-product assistant. Supera a Trimble (teléfono) y Kreo (solo browser).

  POST   /assistant/ask                          → ask question, get AI response
  GET    /assistant/conversations                → list user's conversation threads
  GET    /assistant/conversations/{id}           → full thread with messages
  POST   /assistant/cache/generate               → pre-generate offline responses (Flutter)

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.assistant.schemas import (
    AskRequest,
    AskResponse,
    CacheGenerateRequest,
    CacheGenerateResponse,
    ConversationDetailResponse,
    ConversationResponse,
)
from app.modules.assistant.service import AssistantService

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    data: AskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> AskResponse:
    """Ask the AI assistant a question with optional project context."""
    return await AssistantService.ask(db, org.id, current_user, data)


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[ConversationResponse]:
    return await AssistantService.list_conversations(db, current_user.id, org.id, page)


@router.get("/conversations/{conv_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ConversationDetailResponse:
    return await AssistantService.get_conversation(db, conv_id, current_user.id, org.id)


@router.post("/cache/generate", response_model=CacheGenerateResponse)
async def generate_cache(
    data: CacheGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CacheGenerateResponse:
    """Pre-generate AI responses for offline Flutter cache (Hive)."""
    return await AssistantService.generate_offline_cache(db, org.id, current_user, data)
