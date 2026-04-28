"""
Conduit Tests — Integration: Login, Rate Limiting & Lockout
Prompt 3: "Rate limiting: 5 intentos/15min por IP — Account lockout: 10 intentos → 1hr"

Tests:
- Happy path login returns token pair
- Wrong password returns 401
- Rate limiting per IP (5 attempts)
- Account lockout after 10 failures
- Successful login clears failure counter
- Locked account returns 423

Bliss Systems LLC — APEX Standard
"""

import pytest
from httpx import AsyncClient

from tests.conftest import make_register_payload


class TestLogin:
    async def test_login_success_returns_tokens(self, client: AsyncClient, test_user, free_plan):
        """Happy path: login with correct credentials returns token pair."""
        resp = await client.post("/api/v1/login", json={
            "email": test_user["email"],
            "password": test_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password_returns_401(self, client: AsyncClient, test_user, free_plan):
        """Wrong password must return 401 INVALID_CREDENTIALS."""
        resp = await client.post("/api/v1/login", json={
            "email": test_user["email"],
            "password": "WrongPass999!",
        })
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_CREDENTIALS"

    async def test_login_unknown_email_returns_401(self, client: AsyncClient, free_plan):
        """Non-existent email must not reveal user existence (always 401)."""
        resp = await client.post("/api/v1/login", json={
            "email": "nobody@conduit.build",
            "password": "SomePass123!",
        })
        assert resp.status_code == 401
        # Must not say "user not found" — prevents email enumeration
        assert resp.json()["code"] == "INVALID_CREDENTIALS"

    async def test_login_missing_fields_returns_422(self, client: AsyncClient, free_plan):
        """Incomplete payload must fail validation."""
        resp = await client.post("/api/v1/login", json={"email": "test@conduit.build"})
        assert resp.status_code == 422

    async def test_successful_login_clears_failure_counter(
        self, client: AsyncClient, test_user, free_plan, fake_redis
    ):
        """After successful login, Redis failure counter must be zero."""
        # Fail twice
        for _ in range(2):
            await client.post("/api/v1/login", json={
                "email": test_user["email"],
                "password": "Wrong123!",
            })

        # Succeed
        resp = await client.post("/api/v1/login", json={
            "email": test_user["email"],
            "password": test_user["password"],
        })
        assert resp.status_code == 200

        # Redis counter must be cleared
        count = await fake_redis.get(f"lockout:{test_user['user'].id}")
        assert count is None


class TestRateLimiting:
    async def test_ip_rate_limit_after_5_attempts(
        self, client: AsyncClient, free_plan
    ):
        """
        5 attempts from same IP within window → 429 on 6th.
        Prompt 3: "5 intentos/15min por IP"
        """
        # 5 failed attempts
        for i in range(5):
            await client.post(
                "/api/v1/login",
                json={"email": f"fake{i}@conduit.build", "password": "Any123!"},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )

        # 6th attempt must be rate-limited
        resp = await client.post(
            "/api/v1/login",
            json={"email": "fake5@conduit.build", "password": "Any123!"},
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp.status_code == 429
        assert resp.json()["code"] == "RATE_LIMITED"
        assert "retry_after_seconds" in resp.json()["details"]

    async def test_different_ips_are_rate_limited_independently(
        self, client: AsyncClient, free_plan
    ):
        """Rate limit bucket is per-IP — different IPs are independent."""
        # Fill up IP1
        for i in range(5):
            await client.post(
                "/api/v1/login",
                json={"email": f"x{i}@conduit.build", "password": "Any123!"},
                headers={"X-Forwarded-For": "10.0.0.2"},
            )

        # IP2 should still work
        resp = await client.post(
            "/api/v1/login",
            json={"email": "any@conduit.build", "password": "Any123!"},
            headers={"X-Forwarded-For": "10.0.0.3"},
        )
        # Will get 401 (wrong creds), NOT 429
        assert resp.status_code == 401


class TestAccountLockout:
    async def test_account_locked_after_10_failures(
        self, client: AsyncClient, test_user, free_plan, fake_redis
    ):
        """
        10 failures from same account → 423 ACCOUNT_LOCKED.
        Prompt 3: "10 intentos → lock 1 hora"
        """
        # Simulate 10 failures via Redis (bypassing IP rate limit)
        user_id = str(test_user["user"].id)
        await fake_redis.setex(f"lockout:{user_id}", 3600, 10)

        resp = await client.post("/api/v1/login", json={
            "email": test_user["email"],
            "password": "Wrong123!",
        })
        assert resp.status_code == 423
        assert resp.json()["code"] == "ACCOUNT_LOCKED"
        assert "retry_after_seconds" in resp.json()["details"]

    async def test_locked_account_rejects_correct_password(
        self, client: AsyncClient, test_user, free_plan, fake_redis
    ):
        """Even the correct password must be rejected if account is locked."""
        user_id = str(test_user["user"].id)
        await fake_redis.setex(f"lockout:{user_id}", 3600, 10)

        resp = await client.post("/api/v1/login", json={
            "email": test_user["email"],
            "password": test_user["password"],  # Correct password!
        })
        assert resp.status_code == 423
