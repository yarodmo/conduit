"""
Conduit Tests — Security Monitor (M14) integration tests.

Coverage:
  - Security headers present on every response
  - SQLi pattern detection → 400
  - Path traversal detection → 400
  - Scanner user agent → 400
  - Clean requests pass through
  - GET /security/events (list + filters)
  - GET /security/stats
  - GET /security/digest
  - PATCH /security/events/{id}/resolve
  - POST /security/events/test
  - Beat schedule registered (digest + 3 total)
  - Attack pattern unit tests (regex accuracy)

Bliss Systems LLC — APEX Standard
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import SecurityEvent, SecurityEventType, SecuritySeverity, SEVERITY_MAP
from app.middleware.security import detect_sqli, detect_path_traversal, detect_scanner_ua


# ══════════════════════════════════════
# SECURITY HEADERS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-xss-protection") == "1; mode=block"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "x-request-id" in resp.headers


@pytest.mark.asyncio
async def test_security_headers_on_api_response(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"


@pytest.mark.asyncio
async def test_request_id_unique_per_request(client: AsyncClient):
    resp1 = await client.get("/health")
    resp2 = await client.get("/health")
    assert resp1.headers["x-request-id"] != resp2.headers["x-request-id"]


# ══════════════════════════════════════
# ATTACK DETECTION — middleware blocks
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_sqli_in_query_param_blocked(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/catalog/items",
        params={"category": "'; DROP TABLE users; --"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "blocked" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_path_traversal_in_url_blocked(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/../../../etc/passwd",
        headers=auth_headers,
    )
    assert resp.status_code in (400, 404)


@pytest.mark.asyncio
async def test_scanner_ua_blocked(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/catalog/items",
        headers={**auth_headers, "user-agent": "sqlmap/1.7"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_clean_request_passes(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/catalog/items",
        params={"category": "HVAC"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_check_exempt_from_detection(client: AsyncClient):
    """Health endpoint never blocked — needed for load balancer."""
    resp = await client.get("/health")
    assert resp.status_code == 200


# ══════════════════════════════════════
# SECURITY EVENT ENDPOINTS
# ══════════════════════════════════════

@pytest.fixture
async def security_event(db: AsyncSession, test_user: dict) -> SecurityEvent:
    event = SecurityEvent(
        org_id=test_user["org"].id,
        event_type="sqli_attempt",
        severity="CRITICAL",
        ip_address="1.2.3.4",
        endpoint="/api/v1/catalog/items",
        method="GET",
        details={"param": "category", "value": "1' OR '1'='1"},
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@pytest.mark.asyncio
async def test_list_events_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/security/events", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_events_returns_seeded(
    client: AsyncClient, auth_headers: dict, security_event: SecurityEvent
):
    resp = await client.get("/api/v1/security/events", headers=auth_headers)
    assert resp.status_code == 200
    ids = [e["id"] for e in resp.json()]
    assert str(security_event.id) in ids


@pytest.mark.asyncio
async def test_list_events_filter_by_severity(
    client: AsyncClient, auth_headers: dict, security_event: SecurityEvent
):
    resp = await client.get(
        "/api/v1/security/events",
        params={"severity": "CRITICAL"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    for event in resp.json():
        assert event["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_list_events_filter_unresolved(
    client: AsyncClient, auth_headers: dict, security_event: SecurityEvent
):
    resp = await client.get(
        "/api/v1/security/events",
        params={"unresolved_only": "true"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    for event in resp.json():
        assert event["resolved"] is False


@pytest.mark.asyncio
async def test_list_events_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/security/events")
    assert resp.status_code == 401


# ══════════════════════════════════════
# STATS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_get_stats_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/security/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 0
    assert data["critical_events"] == 0
    assert data["period_days"] == 7


@pytest.mark.asyncio
async def test_get_stats_counts_correctly(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    for severity in ["CRITICAL", "CRITICAL", "HIGH", "LOW"]:
        db.add(SecurityEvent(
            org_id=test_user["org"].id,
            event_type="sqli_attempt",
            severity=severity,
            ip_address="1.2.3.4",
            endpoint="/api/test",
            method="GET",
        ))
    await db.commit()

    resp = await client.get("/api/v1/security/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["critical_events"] == 2
    assert data["high_events"] == 1
    assert data["total_events"] == 4


@pytest.mark.asyncio
async def test_get_stats_custom_period(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/security/stats", params={"days": 30}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 30


# ══════════════════════════════════════
# DIGEST
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_digest_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/security/digest", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "clean" in data["summary"].lower() or "no security events" in data["summary"].lower()


@pytest.mark.asyncio
async def test_digest_with_events(
    client: AsyncClient, auth_headers: dict, security_event: SecurityEvent
):
    resp = await client.get("/api/v1/security/digest", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_critical"] >= 1
    assert "CRITICAL" in data["summary"] or "events detected" in data["summary"]


# ══════════════════════════════════════
# RESOLVE
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_resolve_event(
    client: AsyncClient, auth_headers: dict, security_event: SecurityEvent
):
    resp = await client.patch(
        f"/api/v1/security/events/{security_event.id}/resolve",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is True
    assert data["resolved_at"] is not None


@pytest.mark.asyncio
async def test_resolve_nonexistent_event(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/v1/security/events/{uuid.uuid4()}/resolve",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ══════════════════════════════════════
# TEST EVENT
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_create_test_event(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/security/events/test", headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["event_type"] == "test_event"
    assert data["severity"] == "LOW"
    assert data["ip_address"] == "127.0.0.1"


# ══════════════════════════════════════
# UNIT — attack pattern detection
# ══════════════════════════════════════

def test_sqli_union_select():
    assert detect_sqli("' UNION SELECT * FROM users --") is True


def test_sqli_drop_table():
    assert detect_sqli("1; DROP TABLE plans; --") is True


def test_sqli_or_1_equals_1():
    assert detect_sqli("1' OR '1'='1") is True


def test_sqli_clean_value():
    assert detect_sqli("HVAC equipment 5-ton") is False
    assert detect_sqli("2024-01-15") is False


def test_path_traversal_dotdot():
    assert detect_path_traversal("../../etc/passwd") is True


def test_path_traversal_encoded():
    assert detect_path_traversal("%2e%2e%2fetc%2fpasswd") is True


def test_path_traversal_clean():
    assert detect_path_traversal("/api/v1/catalog/items") is False


def test_scanner_sqlmap():
    assert detect_scanner_ua("sqlmap/1.7.6") is True


def test_scanner_nikto():
    assert detect_scanner_ua("Nikto/2.1.6") is True


def test_scanner_clean_browser():
    assert detect_scanner_ua("Mozilla/5.0 (Macintosh; Intel Mac OS X)") is False


# ══════════════════════════════════════
# UNIT — severity map + beat schedule
# ══════════════════════════════════════

def test_severity_map_critical_types():
    assert SEVERITY_MAP[SecurityEventType.SQLI_ATTEMPT] == SecuritySeverity.CRITICAL
    assert SEVERITY_MAP[SecurityEventType.TENANT_VIOLATION] == SecuritySeverity.CRITICAL


def test_severity_map_high_types():
    assert SEVERITY_MAP[SecurityEventType.PATH_TRAVERSAL] == SecuritySeverity.HIGH
    assert SEVERITY_MAP[SecurityEventType.BRUTE_FORCE] == SecuritySeverity.HIGH


def test_all_event_types_in_severity_map():
    for event_type in SecurityEventType:
        assert event_type in SEVERITY_MAP, f"{event_type} missing from SEVERITY_MAP"


def test_daily_digest_beat_registered():
    from app.tasks.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule
    assert "security-digest-daily" in schedule
    assert schedule["security-digest-daily"]["schedule"] == 86400.0


def test_three_beat_tasks_total():
    from app.tasks.celery_app import celery_app
    assert len(celery_app.conf.beat_schedule) == 3
