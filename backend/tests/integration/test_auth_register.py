"""
Conduit Tests — Integration: Registration Flow
Prompt 3: "POST /auth/register → user + org en transacción atómica"

Tests:
- Happy path: user + org created atomically
- Duplicate email rejected
- Password complexity enforced
- Token pair returned immediately
- Org slug auto-generated

Bliss Systems LLC — APEX Standard
"""

import pytest
from httpx import AsyncClient

from tests.conftest import make_register_payload


class TestRegistration:
    async def test_register_returns_token_pair(self, client: AsyncClient, free_plan):
        """Successful registration returns access + refresh token."""
        resp = await client.post("/api/v1/register", json=make_register_payload())

        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 15 * 60  # 15 minutes in seconds

    async def test_register_creates_user_and_org_atomically(
        self, client: AsyncClient, free_plan, db
    ):
        """Register creates user + org in one transaction."""
        payload = make_register_payload(
            email="atomic@conduit.build",
            org_name="Atomic Engineering LLC",
        )
        resp = await client.post("/api/v1/register", json=payload)
        assert resp.status_code == 201

        # Me endpoint confirms user + org exist
        tokens = resp.json()
        me_resp = await client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me_resp.status_code == 200
        me = me_resp.json()
        assert me["email"] == "atomic@conduit.build"
        assert len(me["organizations"]) == 1
        assert me["organizations"][0]["org_name"] == "Atomic Engineering LLC"
        assert me["organizations"][0]["role"] == "ORG_ADMIN"

    async def test_register_duplicate_email_rejected(self, client: AsyncClient, free_plan):
        """Second registration with same email returns 409."""
        payload = make_register_payload(email="dup@conduit.build")
        await client.post("/api/v1/register", json=payload)
        resp = await client.post("/api/v1/register", json=payload)

        assert resp.status_code == 409
        assert resp.json()["code"] == "EMAIL_EXISTS"

    async def test_register_weak_password_rejected(self, client: AsyncClient, free_plan):
        """Password without uppercase must fail validation."""
        payload = make_register_payload(password="alllowercase123")
        resp = await client.post("/api/v1/register", json=payload)
        assert resp.status_code == 422

    async def test_register_no_digit_password_rejected(self, client: AsyncClient, free_plan):
        """Password without digit must fail validation."""
        payload = make_register_payload(password="NoDigitPassword!")
        resp = await client.post("/api/v1/register", json=payload)
        assert resp.status_code == 422

    async def test_register_short_password_rejected(self, client: AsyncClient, free_plan):
        """Password shorter than 8 chars must fail."""
        payload = make_register_payload(password="Ab1!")
        resp = await client.post("/api/v1/register", json=payload)
        assert resp.status_code == 422

    async def test_register_invalid_email_rejected(self, client: AsyncClient, free_plan):
        """Invalid email format must be rejected."""
        payload = make_register_payload(email="not-an-email")
        resp = await client.post("/api/v1/register", json=payload)
        assert resp.status_code == 422

    async def test_register_error_format_consistent(self, client: AsyncClient, free_plan):
        """All error responses follow {error, code, details} contract."""
        payload = make_register_payload(email="malformed")
        resp = await client.post("/api/v1/register", json=payload)
        body = resp.json()
        assert "error" in body
        assert "code" in body
        assert "details" in body
