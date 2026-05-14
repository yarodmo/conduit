"""
Conduit Tests — AI Assistant (M10) integration tests.

All litellm calls are mocked — no real API usage.

Coverage:
  - POST /assistant/ask → new conversation created, response returned
  - POST /assistant/ask with conversation_id → thread continued
  - GET /assistant/conversations → list user threads
  - GET /assistant/conversations/{id} → full thread
  - GET /assistant/conversations/{id} wrong user → 404
  - Cache hit → from_cache=True
  - Cache miss → from_cache=False
  - context_type routing (all 6 types accepted)
  - POST /assistant/cache/generate → cached_count returned
  - Unauthorized → 401
  - ContextType enum completeness

Bliss Systems LLC — APEX Standard
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import AssistantCache, AssistantConversation, ContextType


# ══════════════════════════════════════
# MOCK HELPERS
# ══════════════════════════════════════

def _mock_claude_response(text: str = "This is a test AI response."):
    """Return a mock litellm completion response."""
    mock = MagicMock()
    mock.choices[0].message.content = text
    mock.usage.total_tokens = 42
    return mock


MOCK_PATH = "app.modules.assistant.service._call_claude"


def _patched(response_text: str = "Test AI response."):
    return patch(MOCK_PATH, return_value=(response_text, 42))


# ══════════════════════════════════════
# ASK — basic
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_ask_creates_conversation(client: AsyncClient, auth_headers: dict):
    with _patched():
        resp = await client.post(
            "/api/v1/assistant/ask",
            json={"message": "How do I create an RFI from a markup?",
                  "context_type": "rfi_help"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "conversation_id" in data
    assert data["message"]["role"] == "assistant"
    assert data["message"]["content"] == "Test AI response."
    assert data["from_cache"] is False


@pytest.mark.asyncio
async def test_ask_continues_existing_conversation(
    client: AsyncClient, auth_headers: dict
):
    with _patched("First answer."):
        resp1 = await client.post(
            "/api/v1/assistant/ask",
            json={"message": "What is a takeoff?", "context_type": "general"},
            headers=auth_headers,
        )
    conv_id = resp1.json()["conversation_id"]

    with _patched("Follow-up answer."):
        resp2 = await client.post(
            "/api/v1/assistant/ask",
            json={"message": "How accurate is it?", "context_type": "general",
                  "conversation_id": conv_id},
            headers=auth_headers,
        )
    assert resp2.status_code == 200
    assert resp2.json()["conversation_id"] == conv_id
    assert resp2.json()["message"]["content"] == "Follow-up answer."


@pytest.mark.asyncio
async def test_ask_all_context_types(client: AsyncClient, auth_headers: dict):
    for ctx in ["takeoff_question", "plan_question", "rfi_help",
                "field_question", "general", "how_to"]:
        with _patched(f"Response for {ctx}"):
            resp = await client.post(
                "/api/v1/assistant/ask",
                json={"message": "Test question for context", "context_type": ctx},
                headers=auth_headers,
            )
        assert resp.status_code == 200, f"Failed for context_type={ctx}: {resp.json()}"


@pytest.mark.asyncio
async def test_ask_message_too_short(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/assistant/ask",
        json={"message": "Hi", "context_type": "general"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ask_unauthorized(client: AsyncClient):
    resp = await client.post(
        "/api/v1/assistant/ask",
        json={"message": "How do I upload a plan?"},
    )
    assert resp.status_code == 401


# ══════════════════════════════════════
# CACHE HIT
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_ask_returns_cached_response(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    project_id = uuid.uuid4()
    question = "What is a takeoff?"
    import hashlib
    key = hashlib.sha256(question.strip().lower().encode()).hexdigest()

    cache_entry = AssistantCache(
        org_id=test_user["org"].id,
        project_id=project_id,
        question_hash=key,
        context_type="general",
        question=question,
        response="Cached: A takeoff is a quantity extraction process.",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    db.add(cache_entry)
    await db.commit()

    with _patched("Should not reach Claude"):
        resp = await client.post(
            "/api/v1/assistant/ask",
            json={"message": question, "context_type": "general",
                  "project_id": str(project_id)},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["from_cache"] is True
    assert "Cached:" in data["message"]["content"]


# ══════════════════════════════════════
# LIST CONVERSATIONS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_list_conversations_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/assistant/conversations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_conversations_after_ask(client: AsyncClient, auth_headers: dict):
    with _patched():
        await client.post(
            "/api/v1/assistant/ask",
            json={"message": "How does field sync work?", "context_type": "field_question"},
            headers=auth_headers,
        )
    resp = await client.get("/api/v1/assistant/conversations", headers=auth_headers)
    assert resp.status_code == 200
    convs = resp.json()
    assert len(convs) >= 1
    assert convs[0]["context_type"] == "field_question"
    assert convs[0]["message_count"] >= 2  # user + assistant


@pytest.mark.asyncio
async def test_list_conversations_pagination(client: AsyncClient, auth_headers: dict):
    with _patched():
        for i in range(3):
            await client.post(
                "/api/v1/assistant/ask",
                json={"message": f"Question number {i + 1} about the platform",
                      "context_type": "general"},
                headers=auth_headers,
            )
    resp = await client.get(
        "/api/v1/assistant/conversations", params={"page": 1}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 3


# ══════════════════════════════════════
# GET CONVERSATION
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_get_conversation_detail(client: AsyncClient, auth_headers: dict):
    with _patched("Detailed answer here."):
        ask_resp = await client.post(
            "/api/v1/assistant/ask",
            json={"message": "Explain the RFI state machine", "context_type": "rfi_help"},
            headers=auth_headers,
        )
    conv_id = ask_resp.json()["conversation_id"]

    resp = await client.get(
        f"/api/v1/assistant/conversations/{conv_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == conv_id
    assert len(data["messages"]) == 2  # user + assistant
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["content"] == "Detailed answer here."
    assert data["messages"][1]["tokens_used"] == 42


@pytest.mark.asyncio
async def test_get_conversation_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"/api/v1/assistant/conversations/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_conversation_wrong_user(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    # Conversation owned by different user
    conv = AssistantConversation(
        user_id=uuid.uuid4(),
        org_id=test_user["org"].id,
        context_type="general",
        title="Other user's question",
    )
    db.add(conv)
    await db.commit()

    resp = await client.get(
        f"/api/v1/assistant/conversations/{conv.id}", headers=auth_headers
    )
    assert resp.status_code == 404


# ══════════════════════════════════════
# OFFLINE CACHE GENERATION
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_generate_offline_cache(client: AsyncClient, auth_headers: dict):
    project_id = str(uuid.uuid4())
    with _patched("Pre-generated offline response."):
        resp = await client.post(
            "/api/v1/assistant/cache/generate",
            json={
                "project_id": project_id,
                "context_types": ["how_to"],
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["cached_count"] > 0  # how_to has 5 questions
    assert "how_to" in data["context_types"]


@pytest.mark.asyncio
async def test_generate_cache_idempotent(client: AsyncClient, auth_headers: dict):
    """Second call with same project should skip already-cached items."""
    project_id = str(uuid.uuid4())
    with _patched("Response 1"):
        resp1 = await client.post(
            "/api/v1/assistant/cache/generate",
            json={"project_id": project_id, "context_types": ["rfi_help"]},
            headers=auth_headers,
        )
    first_count = resp1.json()["cached_count"]

    with _patched("Response 2"):
        resp2 = await client.post(
            "/api/v1/assistant/cache/generate",
            json={"project_id": project_id, "context_types": ["rfi_help"]},
            headers=auth_headers,
        )
    # Nothing new cached — all already present and not expired
    assert resp2.json()["cached_count"] == 0


# ══════════════════════════════════════
# UNIT — ContextType enum
# ══════════════════════════════════════

def test_context_type_enum_values():
    expected = {
        "takeoff_question", "plan_question", "rfi_help",
        "field_question", "general", "how_to",
    }
    actual = {t.value for t in ContextType}
    assert actual == expected


def test_offline_questions_coverage():
    from app.modules.assistant.service import OFFLINE_QUESTIONS
    for ctx_type in ["takeoff_question", "rfi_help", "field_question", "how_to"]:
        assert ctx_type in OFFLINE_QUESTIONS
        assert len(OFFLINE_QUESTIONS[ctx_type]) >= 5
