"""
Conduit Backend — AI Assistant Service (M10)
Claude-powered in-product assistant with project context injection.

Context routing:
  takeoff_question → loads TakeoffJob summary + items
  plan_question    → loads Plan info + page count
  rfi_help         → loads open RFIs
  field_question   → loads WorkZones + latest progress
  general/how_to   → product knowledge base only

Offline cache: pre-generates top N responses per project for Flutter Hive.

Bliss Systems LLC — APEX Standard
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assistant import AssistantCache, AssistantConversation, AssistantMessage, ContextType
from app.models.auth import User
from app.modules.assistant.schemas import (
    AskRequest,
    AskResponse,
    CacheGenerateRequest,
    CacheGenerateResponse,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
)

logger = structlog.get_logger()

CACHE_TTL_HOURS = 24
PRODUCT_CONTEXT = """You are the Conduit AI Assistant — an expert MEP (Mechanical, Electrical, Plumbing) construction intelligence assistant built into the Conduit platform by Bliss Systems LLC.

Your role: help MEP engineers, project managers, and field technicians work faster and smarter.

Conduit capabilities you know about:
- AI Takeoff Engine: extracts MEP components from plan PDFs using Claude Vision
- Plan Viewer: tile-based plan viewer with markup tools
- RFI Management: digital request-for-information with state machine and legal PDF export
- Field Coordination: work zones with GPS, offline-first progress reporting
- Collaboration: real-time multi-user plan markup sessions
- Material Catalog: semantic search with pgvector, CSV import from Ferguson/Wesco
- Change Orders: linked to RFIs, approval workflow

Always be specific, actionable, and reference exact Conduit UI steps when explaining how-to questions.
Keep responses concise (under 300 words unless detail is required).
"""

# Top offline questions pre-generated per context type
OFFLINE_QUESTIONS: dict[str, list[str]] = {
    "takeoff_question": [
        "Why did the AI miss some components in my takeoff?",
        "How do I correct a wrong quantity in the takeoff?",
        "What does 'requires_review' mean on a takeoff item?",
        "How do I export my takeoff to Excel?",
        "What is the confidence score and when should I review it?",
    ],
    "rfi_help": [
        "How do I create an RFI from a markup?",
        "What happens when an RFI is rejected?",
        "How do I assign an RFI to a reviewer?",
        "Can I export an RFI as a PDF?",
        "How do I create a Change Order from a closed RFI?",
    ],
    "field_question": [
        "How do I report progress for my assigned zone?",
        "What do I do when my zone is blocked?",
        "How does offline sync work?",
        "Can I add photos to my progress report?",
        "How do I see which materials I need for this zone?",
    ],
    "how_to": [
        "How do I upload a plan?",
        "How do I invite a team member to my project?",
        "How do I start a collaboration session?",
        "How do I search the material catalog?",
        "How do I generate a project progress report?",
    ],
}


# ── Context builders ───────────────────────────────────────────────────────

async def _build_context(
    db: AsyncSession,
    context_type: str,
    project_id: uuid.UUID | None,
    plan_id: uuid.UUID | None,
    takeoff_job_id: uuid.UUID | None,
    org_id: uuid.UUID,
) -> str:
    parts: list[str] = []

    if project_id:
        from app.models.projects import Project
        project = await db.get(Project, project_id)
        if project:
            parts.append(
                f"PROJECT: {project.name} | Type: {project.type.value} | "
                f"Complexity: {project.complexity.value}"
            )

    if context_type == "takeoff_question" and takeoff_job_id:
        from app.models.takeoff import TakeoffJob, TakeoffItem
        job = await db.get(TakeoffJob, takeoff_job_id)
        if job:
            stmt = select(TakeoffItem).where(TakeoffItem.job_id == takeoff_job_id).limit(20)
            items = (await db.execute(stmt)).scalars().all()
            items_summary = ", ".join(
                f"{i.item_number}:{i.component_type}(qty={i.quantity},conf={i.confidence_pct}%)"
                for i in items
            )
            parts.append(
                f"TAKEOFF: {job.job_number} | Status: {job.status} | "
                f"Total: ${job.total_cost_usd} | Items (sample): {items_summary}"
            )

    elif context_type == "rfi_help" and project_id:
        from app.models.rfis import RFI
        stmt = select(RFI).where(
            RFI.project_id == project_id,
            RFI.org_id == org_id,
            RFI.deleted_at.is_(None),
            RFI.status.in_(["DRAFT", "SUBMITTED", "UNDER_REVIEW"]),
        ).limit(10)
        rfis = (await db.execute(stmt)).scalars().all()
        if rfis:
            rfi_summary = " | ".join(
                f"{r.rfi_number}({r.status},{r.urgency})" for r in rfis
            )
            parts.append(f"OPEN RFIs: {rfi_summary}")

    elif context_type == "field_question" and project_id:
        from app.models.field import WorkZone
        stmt = select(WorkZone).where(
            WorkZone.project_id == project_id,
            WorkZone.org_id == org_id,
            WorkZone.deleted_at.is_(None),
        ).limit(10)
        zones = (await db.execute(stmt)).scalars().all()
        if zones:
            zone_summary = " | ".join(
                f"{z.name}({z.status})" for z in zones
            )
            parts.append(f"WORK ZONES: {zone_summary}")

    elif context_type == "plan_question" and plan_id:
        from app.models.plans import Plan
        plan = await db.get(Plan, plan_id)
        if plan:
            parts.append(f"PLAN: {plan.name} | Status: {plan.status} | Pages: {plan.page_count}")

    return "\n".join(parts) if parts else ""


def _build_system_prompt(context_type: str, project_context: str) -> str:
    system = PRODUCT_CONTEXT
    if project_context:
        system += f"\n\nCURRENT PROJECT CONTEXT:\n{project_context}"
    return system


def _title_from_message(message: str) -> str:
    return message[:80].strip() + ("…" if len(message) > 80 else "")


def _cache_key(question: str) -> str:
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()


async def _check_cache(
    db: AsyncSession,
    project_id: uuid.UUID,
    question: str,
) -> str | None:
    key = _cache_key(question)
    now = datetime.now(tz=timezone.utc)
    stmt = select(AssistantCache).where(
        AssistantCache.project_id == project_id,
        AssistantCache.question_hash == key,
        AssistantCache.expires_at > now,
    )
    cached = (await db.execute(stmt)).scalar_one_or_none()
    return cached.response if cached else None


# ── Claude call ────────────────────────────────────────────────────────────

def _call_claude(
    system_prompt: str,
    messages: list[dict[str, str]],
) -> tuple[str, int]:
    """Call Claude via litellm. Returns (response_text, tokens_used)."""
    try:
        import litellm
        resp = litellm.completion(
            model="claude-haiku-4-5-20251001",
            system=system_prompt,
            messages=messages,
            max_tokens=600,
        )
        content = resp.choices[0].message.content or ""
        tokens = getattr(resp.usage, "total_tokens", 0)
        return content, tokens
    except Exception as e:
        logger.error("assistant_claude_error", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="AI assistant temporarily unavailable. Please try again.",
        )


# ── Assistant service ──────────────────────────────────────────────────────

class AssistantService:

    @staticmethod
    async def ask(
        db: AsyncSession,
        org_id: uuid.UUID,
        current_user: User,
        data: AskRequest,
    ) -> AskResponse:
        # Check cache first (project-scoped questions only)
        from_cache = False
        if data.project_id:
            cached = await _check_cache(db, data.project_id, data.message)
            if cached:
                from_cache = True
                # Still save to conversation thread
                conv = await _get_or_create_conversation(
                    db, current_user.id, org_id, data
                )
                user_msg = AssistantMessage(
                    conversation_id=conv.id,
                    role="user",
                    content=data.message,
                )
                cached_msg = AssistantMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content=f"[cached] {cached}",
                )
                db.add(user_msg)
                db.add(cached_msg)
                await db.commit()
                await db.refresh(cached_msg)
                return AskResponse(
                    conversation_id=conv.id,
                    message=MessageResponse.model_validate(cached_msg),
                    from_cache=True,
                )

        # Build context + call Claude
        project_context = await _build_context(
            db, data.context_type, data.project_id,
            data.plan_id, data.takeoff_job_id, org_id,
        )
        system_prompt = _build_system_prompt(data.context_type, project_context)

        conv = await _get_or_create_conversation(db, current_user.id, org_id, data)

        # Build message history for Claude
        history_stmt = (
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conv.id)
            .order_by(AssistantMessage.created_at)
            .limit(20)  # last 20 messages for context window
        )
        history = (await db.execute(history_stmt)).scalars().all()
        claude_messages = [{"role": m.role, "content": m.content} for m in history]
        claude_messages.append({"role": "user", "content": data.message})

        response_text, tokens = _call_claude(system_prompt, claude_messages)

        # Persist messages
        user_msg = AssistantMessage(
            conversation_id=conv.id, role="user", content=data.message,
        )
        asst_msg = AssistantMessage(
            conversation_id=conv.id, role="assistant",
            content=response_text, tokens_used=tokens,
        )
        db.add(user_msg)
        db.add(asst_msg)
        conv.updated_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(asst_msg)

        return AskResponse(
            conversation_id=conv.id,
            message=MessageResponse.model_validate(asst_msg),
            from_cache=False,
        )

    @staticmethod
    async def list_conversations(
        db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID, page: int = 1,
    ) -> list[ConversationResponse]:
        stmt = (
            select(AssistantConversation)
            .options(selectinload(AssistantConversation.messages))
            .where(
                AssistantConversation.user_id == user_id,
                AssistantConversation.org_id == org_id,
            )
            .order_by(AssistantConversation.updated_at.desc())
            .offset((page - 1) * 20).limit(20)
        )
        convs = (await db.execute(stmt)).scalars().all()
        return [
            ConversationResponse(
                id=c.id,
                context_type=c.context_type,
                title=c.title,
                project_id=c.project_id,
                message_count=len(c.messages),
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in convs
        ]

    @staticmethod
    async def get_conversation(
        db: AsyncSession,
        conv_id: uuid.UUID,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> ConversationDetailResponse:
        stmt = (
            select(AssistantConversation)
            .options(selectinload(AssistantConversation.messages))
            .where(
                AssistantConversation.id == conv_id,
                AssistantConversation.user_id == user_id,
                AssistantConversation.org_id == org_id,
            )
        )
        conv = (await db.execute(stmt)).scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return ConversationDetailResponse(
            id=conv.id,
            context_type=conv.context_type,
            title=conv.title,
            project_id=conv.project_id,
            message_count=len(conv.messages),
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            messages=[MessageResponse.model_validate(m) for m in conv.messages],
        )

    @staticmethod
    async def generate_offline_cache(
        db: AsyncSession,
        org_id: uuid.UUID,
        current_user: User,
        data: CacheGenerateRequest,
    ) -> CacheGenerateResponse:
        """Pre-generate Claude responses for offline Flutter cache."""
        cached_count = 0
        now = datetime.now(tz=timezone.utc)
        expires = now + timedelta(hours=CACHE_TTL_HOURS)

        for context_type in data.context_types:
            questions = OFFLINE_QUESTIONS.get(context_type, [])
            for question in questions:
                key = _cache_key(question)

                # Skip if already cached and not expired
                existing = (await db.execute(
                    select(AssistantCache).where(
                        AssistantCache.project_id == data.project_id,
                        AssistantCache.question_hash == key,
                        AssistantCache.expires_at > now,
                    )
                )).scalar_one_or_none()
                if existing:
                    continue

                project_context = await _build_context(
                    db, context_type, data.project_id, None, None, org_id
                )
                system_prompt = _build_system_prompt(context_type, project_context)
                try:
                    response_text, _ = _call_claude(
                        system_prompt, [{"role": "user", "content": question}]
                    )
                except HTTPException:
                    continue

                # Upsert cache entry
                cache_entry = (await db.execute(
                    select(AssistantCache).where(
                        AssistantCache.project_id == data.project_id,
                        AssistantCache.question_hash == key,
                    )
                )).scalar_one_or_none()

                if cache_entry:
                    cache_entry.response = response_text
                    cache_entry.expires_at = expires
                else:
                    cache_entry = AssistantCache(
                        org_id=org_id,
                        project_id=data.project_id,
                        question_hash=key,
                        context_type=context_type,
                        question=question,
                        response=response_text,
                        expires_at=expires,
                    )
                    db.add(cache_entry)

                cached_count += 1

        await db.commit()
        return CacheGenerateResponse(
            project_id=data.project_id,
            cached_count=cached_count,
            context_types=data.context_types,
        )


async def _get_or_create_conversation(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    data: AskRequest,
) -> AssistantConversation:
    if data.conversation_id:
        stmt = select(AssistantConversation).where(
            AssistantConversation.id == data.conversation_id,
            AssistantConversation.user_id == user_id,
        )
        conv = (await db.execute(stmt)).scalar_one_or_none()
        if conv:
            return conv

    conv = AssistantConversation(
        user_id=user_id,
        org_id=org_id,
        project_id=data.project_id,
        context_type=data.context_type,
        title=_title_from_message(data.message),
    )
    db.add(conv)
    await db.flush()
    return conv
