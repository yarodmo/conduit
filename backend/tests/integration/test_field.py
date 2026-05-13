"""
Conduit Tests — Field Coordination (M6) integration tests.

Coverage:
  - Zone CRUD
  - State machine transitions (valid + invalid)
  - BLOCKED → RFI auto-creation
  - Progress report creation
  - Field dashboard
  - Offline sync push (conflict resolution)
  - Offline sync pull

Bliss Systems LLC — APEX Standard
"""

import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.projects import Project, ProjectComplexity, ProjectType


# ══════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════

@pytest.fixture
def zone_payload() -> dict:
    return {
        "name": "Level 1 — Mechanical Room",
        "description": "Primary HVAC equipment zone",
        "systems": ["HVAC", "Plumbing"],
        "order_index": 0,
    }


@pytest.fixture
def report_payload() -> dict:
    return {
        "progress_pct": 45,
        "status": "IN_PROGRESS",
        "notes": "Ductwork installation 45% complete",
    }


@pytest.fixture
async def project_id(client: AsyncClient, auth_headers: dict, db: AsyncSession) -> str:
    """Create a project and return its ID string."""
    resp = await client.post("/api/v1/projects", json={
        "name": "Field Test Building",
        "type": "commercial",
        "complexity": "standard",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


@pytest.fixture
async def zone_id(client: AsyncClient, auth_headers: dict, project_id: str,
                  zone_payload: dict) -> str:
    """Create a zone and return its ID string."""
    resp = await client.post(
        f"/api/v1/projects/{project_id}/zones",
        json=zone_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


# ══════════════════════════════════════
# ZONE CRUD
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_create_zone(client: AsyncClient, auth_headers: dict,
                           project_id: str, zone_payload: dict):
    resp = await client.post(
        f"/api/v1/projects/{project_id}/zones",
        json=zone_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == zone_payload["name"]
    assert data["status"] == "NOT_STARTED"
    assert data["systems"] == ["HVAC", "Plumbing"]
    assert data["blocked_reason"] is None


@pytest.mark.asyncio
async def test_list_zones(client: AsyncClient, auth_headers: dict,
                          project_id: str, zone_id: str):
    resp = await client.get(
        f"/api/v1/projects/{project_id}/zones",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    zones = resp.json()
    assert len(zones) >= 1
    assert any(z["id"] == zone_id for z in zones)


@pytest.mark.asyncio
async def test_get_zone(client: AsyncClient, auth_headers: dict,
                        project_id: str, zone_id: str):
    resp = await client.get(
        f"/api/v1/projects/{project_id}/zones/{zone_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == zone_id


@pytest.mark.asyncio
async def test_get_zone_not_found(client: AsyncClient, auth_headers: dict, project_id: str):
    import uuid
    resp = await client.get(
        f"/api/v1/projects/{project_id}/zones/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthorized_requires_auth(client: AsyncClient, project_id: str):
    resp = await client.get(f"/api/v1/projects/{project_id}/zones")
    assert resp.status_code == 401


# ══════════════════════════════════════
# STATE MACHINE — VALID TRANSITIONS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_transition_not_started_to_in_progress(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_transition_in_progress_to_completed(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=auth_headers,
    )
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "COMPLETED"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


# ══════════════════════════════════════
# STATE MACHINE — INVALID TRANSITIONS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_invalid_transition_not_started_to_completed(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "COMPLETED"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_transition_completed_to_blocked(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    # Drive to COMPLETED
    for status in ("IN_PROGRESS", "COMPLETED"):
        await client.patch(
            f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
            json={"status": status},
            headers=auth_headers,
        )

    resp = await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "BLOCKED", "blocked_reason": "Trying to re-block"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_status_value(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "FLYING"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ══════════════════════════════════════
# BLOCKED → RFI AUTO-CREATION
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_block_zone_creates_rfi(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    # Move to IN_PROGRESS first
    await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=auth_headers,
    )

    # Block it
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "BLOCKED", "blocked_reason": "Missing structural drawings for wall opening"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "BLOCKED"
    assert data["blocked_reason"] == "Missing structural drawings for wall opening"
    assert data["blocked_rfi_id"] is not None  # auto-created RFI

    # Verify the auto-created RFI is reachable
    rfi_id = data["blocked_rfi_id"]
    rfi_resp = await client.get(f"/api/v1/rfis/{rfi_id}", headers=auth_headers)
    assert rfi_resp.status_code == 200
    rfi_data = rfi_resp.json()
    assert rfi_data["source"] == "FIELD_BLOCKED"
    assert rfi_data["urgency"] == "HIGH"
    assert "FIELD BLOCKED" in rfi_data["title"]


@pytest.mark.asyncio
async def test_block_without_reason_fails(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=auth_headers,
    )
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "BLOCKED"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unblock_zone_clears_blocked_fields(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    for status, payload in [
        ("IN_PROGRESS", {}),
        ("BLOCKED", {"blocked_reason": "Pipe conflict with structural beam"}),
    ]:
        payload["status"] = status
        await client.patch(
            f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
            json=payload,
            headers=auth_headers,
        )

    resp = await client.patch(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "IN_PROGRESS"
    assert data["blocked_reason"] is None
    assert data["blocked_rfi_id"] is None


# ══════════════════════════════════════
# PROGRESS REPORTS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_add_progress_report(
    client: AsyncClient, auth_headers: dict, project_id: str,
    zone_id: str, report_payload: dict
):
    resp = await client.post(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/reports",
        json=report_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["progress_pct"] == 45
    assert data["status"] == "IN_PROGRESS"
    assert data["zone_id"] == zone_id


@pytest.mark.asyncio
async def test_progress_pct_validation(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    resp = await client.post(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/reports",
        json={"progress_pct": 110, "status": "IN_PROGRESS"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_progress_reports(
    client: AsyncClient, auth_headers: dict, project_id: str,
    zone_id: str, report_payload: dict
):
    await client.post(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/reports",
        json=report_payload,
        headers=auth_headers,
    )
    resp = await client.get(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/reports",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    reports = resp.json()
    assert len(reports) >= 1


# ══════════════════════════════════════
# FIELD DASHBOARD
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_field_dashboard_empty_project(
    client: AsyncClient, auth_headers: dict, project_id: str
):
    resp = await client.get(
        f"/api/v1/projects/{project_id}/field-dashboard",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_zones"] == 0
    assert data["completion_pct"] == 0.0
    assert data["blocked_zones"] == []
    assert data["recent_reports"] == []


@pytest.mark.asyncio
async def test_field_dashboard_with_zones(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    # Create another zone and complete it
    resp2 = await client.post(
        f"/api/v1/projects/{project_id}/zones",
        json={"name": "Level 2 — Electrical Room", "systems": ["Electrical"], "order_index": 1},
        headers=auth_headers,
    )
    zone2_id = resp2.json()["id"]

    for status in ("IN_PROGRESS", "COMPLETED"):
        await client.patch(
            f"/api/v1/projects/{project_id}/zones/{zone2_id}/status",
            json={"status": status},
            headers=auth_headers,
        )

    resp = await client.get(
        f"/api/v1/projects/{project_id}/field-dashboard",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_zones"] == 2
    assert data["completed"] == 1
    assert data["not_started"] == 1
    assert data["completion_pct"] == 50.0


@pytest.mark.asyncio
async def test_field_dashboard_standard_project_has_geofencing(
    client: AsyncClient, auth_headers: dict, project_id: str
):
    resp = await client.get(
        f"/api/v1/projects/{project_id}/field-dashboard",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # project_id fixture creates complexity=standard → geofencing_active=True
    assert resp.json()["geofencing_active"] is True


# ══════════════════════════════════════
# OFFLINE SYNC — PUSH
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_sync_push_zone_update(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    resp = await client.post(
        f"/api/v1/projects/{project_id}/sync/push",
        json={
            "zone_updates": [{
                "zone_id": zone_id,
                "status": "IN_PROGRESS",
                "client_updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }],
            "new_reports": [],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted_zone_updates"] == 1
    assert data["conflicts"] == []


@pytest.mark.asyncio
async def test_sync_push_conflict_completed_zone(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    # Drive zone to COMPLETED
    for status in ("IN_PROGRESS", "COMPLETED"):
        await client.patch(
            f"/api/v1/projects/{project_id}/zones/{zone_id}/status",
            json={"status": status},
            headers=auth_headers,
        )

    # Client tries to push IN_PROGRESS → conflict (completed cannot revert)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/sync/push",
        json={
            "zone_updates": [{
                "zone_id": zone_id,
                "status": "IN_PROGRESS",
                "client_updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }],
            "new_reports": [],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted_zone_updates"] == 0
    assert len(data["conflicts"]) == 1
    assert data["conflicts"][0]["server_status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_sync_push_new_reports(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    resp = await client.post(
        f"/api/v1/projects/{project_id}/sync/push",
        json={
            "zone_updates": [],
            "new_reports": [{
                "zone_id": zone_id,
                "progress_pct": 30,
                "status": "IN_PROGRESS",
                "notes": "Offline report from field",
                "client_created_at": datetime.now(tz=timezone.utc).isoformat(),
            }],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted_reports"] == 1


# ══════════════════════════════════════
# OFFLINE SYNC — PULL
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_sync_pull_returns_recent_zones(
    client: AsyncClient, auth_headers: dict, project_id: str, zone_id: str
):
    since = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat()
    resp = await client.get(
        f"/api/v1/projects/{project_id}/sync/pull",
        params={"since": since},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "zones" in data
    assert "reports" in data
    assert "server_time" in data


@pytest.mark.asyncio
async def test_sync_pull_filters_by_since(
    client: AsyncClient, auth_headers: dict, project_id: str
):
    # Pull from far future — should return no zones
    since = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    resp = await client.get(
        f"/api/v1/projects/{project_id}/sync/pull",
        params={"since": since},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["zones"] == []
