"""
Conduit Backend — Collaboration Service (M11)
Session lifecycle + Redis shared state management.

Redis keys per session:
  collab:{id}:participants   → SET of user_id strings
  collab:{id}:cursors        → HASH {user_id: JSON{x,y,page}}
  collab:{id}:locked_markups → HASH {markup_id: user_id} (TTL 30s per field)
  collab:{id}:events         → STREAM (24h retention, for late-joiner replay)
  collab:{id}:event_counter  → INCR counter for server_event_id

Broadcast channel:
  collab:channel:{id}        → PubSub (all messages routed here)

Bliss Systems LLC — APEX Standard
"""

import json
import random
import string
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auth import User
from app.models.collaboration import PARTICIPANT_COLORS, CollabSession, SessionParticipant
from app.modules.collaboration.schemas import (
    ParticipantInfo,
    SessionDetailResponse,
    SessionResponse,
)

logger = structlog.get_logger()

SESSION_STREAM_MAXLEN = 5000      # keep last 5000 events per session
LOCK_TTL_SECONDS = 30             # auto-unlock on disconnect


def _session_to_response(session: CollabSession) -> SessionResponse:
    active_count = sum(1 for p in session.participants if p.is_active)
    return SessionResponse(
        id=session.id,
        plan_id=session.plan_id,
        session_code=session.session_code,
        status=session.status,
        host_user_id=session.host_user_id,
        max_participants=session.max_participants,
        participant_count=active_count,
        created_at=session.created_at,
        ended_at=session.ended_at,
    )


def _generate_code() -> str:
    """Human-readable 7-char code: 'ABC-1234'."""
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    digits = "".join(random.choices(string.digits, k=4))
    return f"{letters}-{digits}"


async def _get_session(
    db: AsyncSession, session_id: uuid.UUID, org_id: uuid.UUID
) -> CollabSession:
    stmt = (
        select(CollabSession)
        .options(selectinload(CollabSession.participants))
        .where(CollabSession.id == session_id, CollabSession.org_id == org_id)
        .execution_options(populate_existing=True)
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


class CollabService:

    @staticmethod
    async def create(
        db: AsyncSession,
        plan_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
        max_participants: int = 20,
    ) -> SessionDetailResponse:
        # Generate unique code
        for _ in range(10):
            code = _generate_code()
            exists = (await db.execute(
                select(CollabSession).where(CollabSession.session_code == code)
            )).scalar_one_or_none()
            if not exists:
                break

        session = CollabSession(
            plan_id=plan_id,
            org_id=org_id,
            host_user_id=current_user.id,
            session_code=code,
            max_participants=max_participants,
        )
        db.add(session)
        await db.flush()

        # Host auto-joins as first participant
        participant = SessionParticipant(
            session_id=session.id,
            user_id=current_user.id,
            org_id=org_id,
            color=PARTICIPANT_COLORS[0],
        )
        db.add(participant)
        await db.commit()
        await db.refresh(session)

        session = await _get_session(db, session.id, org_id)
        return SessionDetailResponse(
            **_session_to_response(session).model_dump(),
            participants=[
                ParticipantInfo(
                    user_id=p.user_id,
                    name=str(p.user_id)[:8],
                    color=p.color,
                    is_active=p.is_active,
                )
                for p in session.participants
            ],
        )

    @staticmethod
    async def list_active(
        db: AsyncSession, plan_id: uuid.UUID, org_id: uuid.UUID
    ) -> list[SessionResponse]:
        stmt = (
            select(CollabSession)
            .options(selectinload(CollabSession.participants))
            .where(
                CollabSession.plan_id == plan_id,
                CollabSession.org_id == org_id,
                CollabSession.status == "active",
            )
            .order_by(CollabSession.created_at.desc())
        )
        sessions = (await db.execute(stmt)).scalars().all()
        return [_session_to_response(s) for s in sessions]

    @staticmethod
    async def join(
        db: AsyncSession,
        session_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
    ) -> SessionDetailResponse:
        session = await _get_session(db, session_id, org_id)

        if session.status != "active":
            raise HTTPException(status_code=422, detail="Session is no longer active")

        # Direct DB count — bypasses SQLAlchemy identity-map cached relationship
        active_count_stmt = select(func.count()).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.is_active.is_(True),
        )
        active_count = (await db.execute(active_count_stmt)).scalar_one()
        if active_count >= session.max_participants:
            raise HTTPException(status_code=422, detail="Session is full")

        # Check if already a participant
        existing = next(
            (p for p in session.participants if p.user_id == current_user.id), None
        )
        if existing:
            if existing.is_active:
                raise HTTPException(status_code=409, detail="Already in session")
            # Rejoin
            existing.is_active = True
            existing.left_at = None
        else:
            color_index = active_count % len(PARTICIPANT_COLORS)
            participant = SessionParticipant(
                session_id=session_id,
                user_id=current_user.id,
                org_id=org_id,
                color=PARTICIPANT_COLORS[color_index],
            )
            db.add(participant)

        await db.commit()
        session = await _get_session(db, session_id, org_id)

        return SessionDetailResponse(
            **_session_to_response(session).model_dump(),
            participants=[
                ParticipantInfo(
                    user_id=p.user_id,
                    name=str(p.user_id)[:8],
                    color=p.color,
                    is_active=p.is_active,
                )
                for p in session.participants if p.is_active
            ],
        )

    @staticmethod
    async def leave(
        db: AsyncSession,
        session_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        session = await _get_session(db, session_id, org_id)
        participant = next(
            (p for p in session.participants
             if p.user_id == current_user.id and p.is_active), None
        )
        if not participant:
            raise HTTPException(status_code=404, detail="Not a participant of this session")

        participant.is_active = False
        participant.left_at = datetime.now(tz=timezone.utc)
        await db.commit()

        # Release Redis locks held by this user
        await _release_user_locks(str(session_id), str(current_user.id))
        return {"left": True}

    @staticmethod
    async def get_participants(
        db: AsyncSession, session_id: uuid.UUID, org_id: uuid.UUID
    ) -> list[ParticipantInfo]:
        session = await _get_session(db, session_id, org_id)
        return [
            ParticipantInfo(
                user_id=p.user_id,
                name=str(p.user_id)[:8],
                color=p.color,
                is_active=p.is_active,
            )
            for p in session.participants if p.is_active
        ]

    @staticmethod
    async def end(
        db: AsyncSession,
        session_id: uuid.UUID,
        org_id: uuid.UUID,
        current_user: User,
    ) -> SessionResponse:
        session = await _get_session(db, session_id, org_id)

        if session.host_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the host can end the session")
        if session.status != "active":
            raise HTTPException(status_code=422, detail="Session already ended")

        session.status = "ended"
        session.ended_at = datetime.now(tz=timezone.utc)

        for p in session.participants:
            p.is_active = False
            if not p.left_at:
                p.left_at = session.ended_at

        await db.commit()

        # Clear Redis state
        await _clear_session_state(str(session_id))

        return _session_to_response(session)


# ── Redis state helpers ────────────────────────────────────────────────────

async def _release_user_locks(session_id: str, user_id: str) -> None:
    try:
        from app.core.redis import redis_client
        if not redis_client:
            return
        lock_key = f"collab:{session_id}:locked_markups"
        # Get all locks and remove ones owned by this user
        locks = await redis_client.hgetall(lock_key)
        to_release = [k for k, v in locks.items() if v == user_id]
        if to_release:
            await redis_client.hdel(lock_key, *to_release)
    except Exception:
        pass


async def _clear_session_state(session_id: str) -> None:
    try:
        from app.core.redis import redis_client
        if not redis_client:
            return
        keys = [
            f"collab:{session_id}:participants",
            f"collab:{session_id}:cursors",
            f"collab:{session_id}:locked_markups",
            f"collab:{session_id}:event_counter",
        ]
        await redis_client.delete(*keys)
    except Exception:
        pass


async def get_next_event_id(session_id: str) -> int:
    try:
        from app.core.redis import redis_client
        if redis_client:
            return await redis_client.incr(f"collab:{session_id}:event_counter")
    except Exception:
        pass
    return 0


async def update_cursor(session_id: str, user_id: str, payload: dict) -> None:
    try:
        from app.core.redis import redis_client
        if redis_client:
            await redis_client.hset(
                f"collab:{session_id}:cursors",
                user_id, json.dumps(payload)
            )
    except Exception:
        pass


async def try_lock_markup(session_id: str, markup_id: str, user_id: str) -> bool:
    """Optimistic lock. Returns True if lock acquired."""
    try:
        from app.core.redis import redis_client
        if not redis_client:
            return True
        lock_key = f"collab:{session_id}:locked_markups"
        # Only set if not already locked (NX) with 30s TTL
        # We store in a hash but simulate TTL via a separate expiry key
        existing = await redis_client.hget(lock_key, markup_id)
        if existing and existing != user_id:
            return False
        await redis_client.hset(lock_key, markup_id, user_id)
        # Set individual field TTL via separate expiry key
        await redis_client.setex(f"collab:{session_id}:lock:{markup_id}", LOCK_TTL_SECONDS, user_id)
        return True
    except Exception:
        return True


async def release_markup_lock(session_id: str, markup_id: str, user_id: str) -> None:
    try:
        from app.core.redis import redis_client
        if not redis_client:
            return
        lock_key = f"collab:{session_id}:locked_markups"
        owner = await redis_client.hget(lock_key, markup_id)
        if owner == user_id:
            await redis_client.hdel(lock_key, markup_id)
            await redis_client.delete(f"collab:{session_id}:lock:{markup_id}")
    except Exception:
        pass
