"""
Conduit Tests — Integration: Token Refresh & Logout
Prompt 3: "Refresh tokens rotativos — cada uso genera nuevo token"
Prompt 3: "POST /auth/logout → invalidar refresh token (Redis blacklist)"

Tests:
- Refresh returns new token pair
- Old refresh token is invalidated after rotation
- Reuse of rotated token returns 401
- Logout blacklists the refresh token
- Using blacklisted token returns 401
- Access token for /me works until expiry

Bliss Systems LLC — APEX Standard
"""

import pytest
from httpx import AsyncClient


class TestTokenRefresh:
    async def test_refresh_returns_new_token_pair(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Refresh endpoint returns new access + refresh token pair."""
        resp = await client.post("/api/v1/refresh", json={
            "refresh_token": auth_headers["refresh_token"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_refresh_token_rotates(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """New refresh token must differ from old one (rotation)."""
        old_refresh = auth_headers["refresh_token"]
        resp = await client.post("/api/v1/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp.status_code == 200
        new_refresh = resp.json()["refresh_token"]
        assert new_refresh != old_refresh

    async def test_old_refresh_token_rejected_after_rotation(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """
        Old refresh token must be invalidated after rotation.
        Prompt 3: "cada uso genera nuevo token" — reuse = attack.
        """
        old_refresh = auth_headers["refresh_token"]

        # First refresh — valid
        resp = await client.post("/api/v1/refresh", json={"refresh_token": old_refresh})
        assert resp.status_code == 200

        # Second refresh with OLD token — must fail
        resp2 = await client.post("/api/v1/refresh", json={"refresh_token": old_refresh})
        assert resp2.status_code == 401
        assert resp2.json()["code"] == "TOKEN_REVOKED"

    async def test_invalid_refresh_token_rejected(
        self, client: AsyncClient, free_plan, test_user
    ):
        """Completely invalid refresh token must return 401."""
        resp = await client.post("/api/v1/refresh", json={
            "refresh_token": "not-a-real-token",
        })
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_REFRESH"

    async def test_new_access_token_works_for_me(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """New access token from refresh can access protected endpoints."""
        # Get new pair
        resp = await client.post("/api/v1/refresh", json={
            "refresh_token": auth_headers["refresh_token"],
        })
        new_tokens = resp.json()

        # Use new access token
        me_resp = await client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        )
        assert me_resp.status_code == 200


class TestLogout:
    async def test_logout_succeeds(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Logout returns 200 with success message."""
        resp = await client.post(
            "/api/v1/logout",
            json={"refresh_token": auth_headers["refresh_token"]},
            headers={"Authorization": auth_headers["Authorization"]},
        )
        assert resp.status_code == 200
        assert "logged out" in resp.json()["message"].lower()

    async def test_logout_invalidates_refresh_token(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """After logout, the refresh token must be rejected."""
        refresh_token = auth_headers["refresh_token"]

        # Logout
        await client.post(
            "/api/v1/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": auth_headers["Authorization"]},
        )

        # Attempt to refresh with revoked token
        resp = await client.post("/api/v1/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401
        assert resp.json()["code"] == "TOKEN_REVOKED"

    async def test_unauthenticated_logout_rejected(self, client: AsyncClient, free_plan, test_user):
        """Logout without bearer token must return 401."""
        resp = await client.post(
            "/api/v1/logout",
            json={"refresh_token": "any-token"},
        )
        assert resp.status_code == 401
