"""
Conduit Tests — Notifications (M8) integration tests.

Coverage:
  - List notifications (paginated)
  - Unread count badge
  - Mark single read
  - Mark all read
  - Soft-delete
  - Get/update preferences
  - FCM token register (upsert)
  - FCM token invalidate
  - FCM token list

Bliss Systems LLC — APEX Standard
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import Notification, NotificationType


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

async def _seed_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    notif_type: str = "rfi_assigned",
    is_read: bool = False,
) -> Notification:
    n = Notification(
        user_id=user_id,
        org_id=org_id,
        type=notif_type,
        title="Test notification",
        body="Something happened",
        is_read=is_read,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


# ══════════════════════════════════════
# LIST & UNREAD COUNT
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_list_notifications_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["unread_count"] == 0


@pytest.mark.asyncio
async def test_list_notifications_with_data(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    user = test_user["user"]
    org = test_user["org"]
    await _seed_notification(db, user.id, org.id, is_read=False)
    await _seed_notification(db, user.id, org.id, is_read=True)

    resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["unread_count"] == 1
    # Unread appears first
    assert data["items"][0]["is_read"] is False


@pytest.mark.asyncio
async def test_unread_count_endpoint(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    user = test_user["user"]
    org = test_user["org"]
    await _seed_notification(db, user.id, org.id)
    await _seed_notification(db, user.id, org.id)

    resp = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 2


@pytest.mark.asyncio
async def test_pagination(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    user = test_user["user"]
    org = test_user["org"]
    for _ in range(5):
        await _seed_notification(db, user.id, org.id)

    resp = await client.get(
        "/api/v1/notifications", headers=auth_headers,
        params={"page": 1, "page_size": 2}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


# ══════════════════════════════════════
# MARK READ / DELETE
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_mark_single_read(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    n = await _seed_notification(db, test_user["user"].id, test_user["org"].id)
    assert n.is_read is False

    resp = await client.patch(
        f"/api/v1/notifications/{n.id}/mark-read",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True


@pytest.mark.asyncio
async def test_mark_read_wrong_user(
    client: AsyncClient, auth_headers: dict, db: AsyncSession
):
    # Notification belonging to a random other user
    n = Notification(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        type="rfi_assigned",
        title="Other user notif",
        body="nope",
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)

    resp = await client.patch(
        f"/api/v1/notifications/{n.id}/mark-read",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    for _ in range(3):
        await _seed_notification(db, test_user["user"].id, test_user["org"].id)

    resp = await client.post("/api/v1/notifications/mark-all-read", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["marked"] == 3

    count_resp = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert count_resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_delete_notification(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    n = await _seed_notification(db, test_user["user"].id, test_user["org"].id)

    resp = await client.delete(
        f"/api/v1/notifications/{n.id}", headers=auth_headers
    )
    assert resp.status_code == 204

    # Soft-deleted — not visible in list
    list_resp = await client.get("/api/v1/notifications", headers=auth_headers)
    ids = [item["id"] for item in list_resp.json()["items"]]
    assert str(n.id) not in ids


@pytest.mark.asyncio
async def test_unauthorized_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 401


# ══════════════════════════════════════
# PREFERENCES
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_get_preferences_returns_defaults(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/notifications/preferences", headers=auth_headers)
    assert resp.status_code == 200
    prefs = resp.json()
    # In-app always true by default
    assert prefs["rfi_assigned"]["in_app"] is True
    # Email enabled by default for rfi_assigned
    assert prefs["rfi_assigned"]["email"] is True
    # Push enabled for rfi_assigned
    assert prefs["rfi_assigned"]["push"] is True
    # Email NOT enabled by default for plan_new_version
    assert prefs["plan_new_version"]["email"] is False


@pytest.mark.asyncio
async def test_update_preferences(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.put(
        "/api/v1/notifications/preferences",
        headers=auth_headers,
        json={
            "rfi_assigned": {"in_app": True, "email": False, "push": True},
            "takeoff_completed": {"in_app": True, "email": True, "push": False},
        },
    )
    assert resp.status_code == 200
    prefs = resp.json()
    assert prefs["rfi_assigned"]["email"] is False
    assert prefs["takeoff_completed"]["push"] is False


@pytest.mark.asyncio
async def test_update_preferences_idempotent(
    client: AsyncClient, auth_headers: dict
):
    # Second update overwrites first
    payload = {"rfi_answered": {"in_app": True, "email": False, "push": False}}
    await client.put("/api/v1/notifications/preferences",
                     headers=auth_headers, json=payload)
    resp = await client.put("/api/v1/notifications/preferences",
                            headers=auth_headers, json=payload)
    assert resp.status_code == 200
    assert resp.json()["rfi_answered"]["email"] is False


# ══════════════════════════════════════
# FCM TOKENS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_register_fcm_token(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/devices/fcm-token",
        headers=auth_headers,
        json={
            "token": "fcm_test_token_abc123xyz",
            "device_name": "Field Phone",
            "platform": "android",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["token"] == "fcm_test_token_abc123xyz"
    assert data["platform"] == "android"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_same_token_upserts(client: AsyncClient, auth_headers: dict):
    token_val = "fcm_upsert_test_token_999"
    await client.post("/api/v1/devices/fcm-token", headers=auth_headers,
                      json={"token": token_val, "platform": "ios"})
    resp = await client.post("/api/v1/devices/fcm-token", headers=auth_headers,
                             json={"token": token_val, "platform": "ios",
                                   "device_name": "Updated Name"})
    assert resp.status_code == 201
    # Still active after second register
    assert resp.json()["is_active"] is True

    # Only one token in list
    list_resp = await client.get("/api/v1/devices/fcm-tokens", headers=auth_headers)
    tokens = [t for t in list_resp.json() if t["token"] == token_val]
    assert len(tokens) == 1


@pytest.mark.asyncio
async def test_list_fcm_tokens(client: AsyncClient, auth_headers: dict):
    for i in range(3):
        await client.post("/api/v1/devices/fcm-token", headers=auth_headers,
                          json={"token": f"fcm_list_token_{i}", "platform": "android"})

    resp = await client.get("/api/v1/devices/fcm-tokens", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 3


@pytest.mark.asyncio
async def test_invalidate_fcm_token(client: AsyncClient, auth_headers: dict):
    reg = await client.post(
        "/api/v1/devices/fcm-token", headers=auth_headers,
        json={"token": "fcm_to_invalidate_xyz", "platform": "android"},
    )
    token_id = reg.json()["id"]

    resp = await client.delete(
        f"/api/v1/devices/fcm-token/{token_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    # No longer in active list
    list_resp = await client.get("/api/v1/devices/fcm-tokens", headers=auth_headers)
    ids = [t["id"] for t in list_resp.json()]
    assert token_id not in ids


@pytest.mark.asyncio
async def test_invalidate_wrong_user_token(
    client: AsyncClient, auth_headers: dict, db: AsyncSession
):
    from app.models.notifications import FCMToken
    from datetime import datetime, timezone
    t = FCMToken(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        token="fcm_other_user_token",
        platform="ios",
        last_used_at=datetime.now(tz=timezone.utc),
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)

    resp = await client.delete(
        f"/api/v1/devices/fcm-token/{t.id}", headers=auth_headers
    )
    assert resp.status_code == 404
