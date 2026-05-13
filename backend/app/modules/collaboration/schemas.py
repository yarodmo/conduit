"""Conduit Backend — Collaboration Schemas (M11). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── Session ───────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    max_participants: int = 20


class ParticipantInfo(BaseModel):
    user_id: uuid.UUID
    name: str
    color: str
    is_active: bool

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    session_code: str
    status: str
    host_user_id: uuid.UUID
    max_participants: int
    participant_count: int
    created_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}


class SessionDetailResponse(SessionResponse):
    participants: list[ParticipantInfo]


# ── WebSocket message protocol ─────────────────────────────────────────────

# Types accepted from client
WS_CLIENT_TYPES = frozenset({
    "cursor_move",
    "markup_create",
    "markup_update",
    "markup_delete",
    "markup_lock",
    "markup_unlock",
    "selection_change",
    "chat_message",
    "view_change",
    "ping",
})

# Server → client broadcast envelope
class WSBroadcast(BaseModel):
    type: str
    session_id: str
    from_user: dict[str, str]  # {id, name, color}
    payload: dict[str, Any]
    server_timestamp: str
    server_event_id: int
