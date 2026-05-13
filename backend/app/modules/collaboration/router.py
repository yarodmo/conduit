"""
Conduit Backend — Collaboration Router (M11)
Anti-Bluebeam Studio: multi-user real-time plan sessions.

HTTP:
  POST   /plans/{plan_id}/sessions            → create session (host auto-joins)
  GET    /plans/{plan_id}/sessions            → list active sessions for plan
  POST   /sessions/{session_id}/join          → join session
  POST   /sessions/{session_id}/leave         → leave session
  GET    /sessions/{session_id}/participants  → list active participants
  POST   /sessions/{session_id}/end           → end session (host only)

WebSocket:
  WS     /sessions/{session_id}/ws            → real-time collab channel

WebSocket protocol (client → server):
  {
    "type": "cursor_move"|"markup_create"|"markup_update"|"markup_delete"|
            "markup_lock"|"markup_unlock"|"selection_change"|
            "chat_message"|"view_change"|"ping",
    "payload": { ... },
    "client_uuid": "uuid (for dedup)"
  }

Server broadcasts to ALL other participants via Redis Pub/Sub:
  {
    "type": "...",
    "session_id": "...",
    "from_user": {"id": "...", "color": "..."},
    "payload": { ... },
    "server_timestamp": "ISO8601",
    "server_event_id": int
  }

Bliss Systems LLC — APEX Standard
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.collaboration.schemas import (
    ParticipantInfo,
    SessionCreate,
    SessionDetailResponse,
    SessionResponse,
    WS_CLIENT_TYPES,
)
from app.modules.collaboration.service import (
    CollabService,
    get_next_event_id,
    release_markup_lock,
    try_lock_markup,
    update_cursor,
    _release_user_locks,
)

router = APIRouter(tags=["Collaboration"])
logger = structlog.get_logger()


# ── HTTP endpoints ─────────────────────────────────────────────────────────

@router.post("/plans/{plan_id}/sessions",
             response_model=SessionDetailResponse, status_code=201)
async def create_session(
    plan_id: uuid.UUID,
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SessionDetailResponse:
    return await CollabService.create(
        db, plan_id, org.id, current_user, data.max_participants
    )


@router.get("/plans/{plan_id}/sessions", response_model=list[SessionResponse])
async def list_sessions(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[SessionResponse]:
    return await CollabService.list_active(db, plan_id, org.id)


@router.post("/sessions/{session_id}/join", response_model=SessionDetailResponse)
async def join_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SessionDetailResponse:
    return await CollabService.join(db, session_id, org.id, current_user)


@router.post("/sessions/{session_id}/leave")
async def leave_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    return await CollabService.leave(db, session_id, org.id, current_user)


@router.get("/sessions/{session_id}/participants",
            response_model=list[ParticipantInfo])
async def get_participants(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[ParticipantInfo]:
    return await CollabService.get_participants(db, session_id, org.id)


@router.post("/sessions/{session_id}/end", response_model=SessionResponse)
async def end_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SessionResponse:
    result = await CollabService.end(db, session_id, org.id, current_user)

    # Broadcast session_ended to all connected WS clients
    try:
        from app.core.redis import redis_client
        from app.core.config import settings
        import redis.asyncio as aioredis
        r = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.publish(
            f"collab:channel:{session_id}",
            json.dumps({"type": "session_ended", "session_id": str(session_id)}),
        )
        await r.aclose()
    except Exception:
        pass

    return result


# ── WebSocket endpoint ─────────────────────────────────────────────────────

@router.websocket("/sessions/{session_id}/ws")
async def collab_ws(
    websocket: WebSocket,
    session_id: uuid.UUID,
    user_id: str,       # passed as query param (token auth not possible in WS easily)
    user_color: str = "#1E88E5",
) -> None:
    """
    Real-time collaboration WebSocket.

    Connect with: ws://.../sessions/{id}/ws?user_id={uuid}&user_color=%231E88E5

    Client → Server JSON: {"type": ..., "payload": {...}, "client_uuid": "..."}
    Server → Client broadcasts all other participants' events.
    """
    from app.core.config import settings
    import redis.asyncio as aioredis

    await websocket.accept()
    session_str = str(session_id)
    channel = f"collab:channel:{session_str}"

    r = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)

    # Register presence in Redis
    try:
        from app.core.redis import redis_client
        if redis_client:
            await redis_client.sadd(f"collab:{session_str}:participants", user_id)
    except Exception:
        pass

    async def _broadcast_join():
        event_id = await get_next_event_id(session_str)
        msg = json.dumps({
            "type": "user_joined",
            "session_id": session_str,
            "from_user": {"id": user_id, "color": user_color},
            "payload": {},
            "server_timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "server_event_id": event_id,
        })
        await r.publish(channel, msg)

    async def _broadcast_leave():
        await _release_user_locks(session_str, user_id)
        event_id = await get_next_event_id(session_str)
        msg = json.dumps({
            "type": "user_left",
            "session_id": session_str,
            "from_user": {"id": user_id, "color": user_color},
            "payload": {},
            "server_timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "server_event_id": event_id,
        })
        await r.publish(channel, msg)

    async def _listen_redis():
        """Forward Redis pub/sub messages → WS client (skip own messages)."""
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                # Don't echo own messages back
                if data.get("from_user", {}).get("id") == user_id:
                    continue
                await websocket.send_json(data)
                # Terminate WS cleanly on session_ended
                if data.get("type") == "session_ended":
                    break
            except Exception:
                break

    async def _listen_client():
        """Receive client messages, process + broadcast."""
        async for raw in websocket.iter_json():
            msg_type = raw.get("type", "")
            payload = raw.get("payload", {})

            if msg_type not in WS_CLIENT_TYPES:
                await websocket.send_json({"type": "error", "detail": f"Unknown type: {msg_type}"})
                continue

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # Handle special types with Redis state mutations
            if msg_type == "cursor_move":
                await update_cursor(session_str, user_id, payload)

            elif msg_type == "markup_lock":
                markup_id = payload.get("markup_id", "")
                acquired = await try_lock_markup(session_str, markup_id, user_id)
                if not acquired:
                    await websocket.send_json({
                        "type": "markup_lock_denied",
                        "payload": {"markup_id": markup_id},
                    })
                    continue

            elif msg_type == "markup_unlock":
                markup_id = payload.get("markup_id", "")
                await release_markup_lock(session_str, markup_id, user_id)

            # Broadcast to all other participants
            event_id = await get_next_event_id(session_str)
            broadcast = json.dumps({
                "type": msg_type,
                "session_id": session_str,
                "from_user": {"id": user_id, "color": user_color},
                "payload": payload,
                "server_timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "server_event_id": event_id,
                "client_uuid": raw.get("client_uuid", ""),
            })
            await r.publish(channel, broadcast)

    try:
        await _broadcast_join()
        # Run Redis listener + client listener concurrently
        await asyncio.gather(
            _listen_redis(),
            _listen_client(),
            return_exceptions=True,
        )
    except WebSocketDisconnect:
        pass
    finally:
        await _broadcast_leave()
        try:
            from app.core.redis import redis_client
            if redis_client:
                await redis_client.srem(f"collab:{session_str}:participants", user_id)
        except Exception:
            pass
        await pubsub.unsubscribe(channel)
        await r.aclose()
        try:
            await websocket.close()
        except Exception:
            pass
