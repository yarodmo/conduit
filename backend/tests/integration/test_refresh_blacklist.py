"""
FORENSIC TEST — GAP-003: Refresh Token Blacklist (Integration)
==============================================================
Validates end-to-end that:
  1. Logout correctly blacklists the refresh token in Redis
  2. Blacklisted token is rejected on refresh attempt (fast-fail)
  3. Token rotation: old token blacklisted, new token works
  4. Replay attack after logout is rejected within same window
  5. Two concurrent sessions do not interfere with each other

Bliss Systems LLC — APEX Standard | Sprint 1 Validation
"""

import pytest
from httpx import AsyncClient


REGISTER_URL  = "/api/v1/register"
LOGIN_URL     = "/api/v1/login"
REFRESH_URL   = "/api/v1/refresh"
LOGOUT_URL    = "/api/v1/logout"
ME_URL        = "/api/v1/me"


def fresh_user(suffix: str) -> dict:
    return {
        "email":     f"gap003_{suffix}@conduit.build",
        "password":  "Gap003Test!",
        "full_name": f"GAP-003 User {suffix}",
        "org_name":  f"GAP-003 Org {suffix}",
    }


async def register_and_login(client: AsyncClient, suffix: str, free_plan) -> dict:
    """Register + login, return full token dict."""
    await client.post(REGISTER_URL, json=fresh_user(suffix))
    resp = await client.post(LOGIN_URL, json={
        "email":    fresh_user(suffix)["email"],
        "password": fresh_user(suffix)["password"],
    })
    assert resp.status_code == 200
    return resp.json()


# ════════════════════════════════════════════════════
# GAP-003-A: Blacklist + Replay prevention
# ════════════════════════════════════════════════════
class TestRefreshTokenBlacklistIntegration:

    @pytest.mark.asyncio
    async def test_logout_blacklists_refresh_token(
        self, client: AsyncClient, free_plan
    ):
        tokens = await register_and_login(client, "logout_blist", free_plan)
        access  = tokens["access_token"]
        refresh = tokens["refresh_token"]

        # Logout
        logout_resp = await client.post(LOGOUT_URL, headers={
            "Authorization": f"Bearer {access}",
        }, json={"refresh_token": refresh})
        assert logout_resp.status_code == 200

        # Attempt to use the same refresh token — must be rejected
        replay_resp = await client.post(REFRESH_URL, json={"refresh_token": refresh})
        assert replay_resp.status_code in (401, 403), (
            "Blacklisted refresh token accepted — GAP-003 NOT fixed!"
        )

    @pytest.mark.asyncio
    async def test_replay_attack_after_logout_rejected(
        self, client: AsyncClient, free_plan
    ):
        tokens = await register_and_login(client, "replay_atk", free_plan)
        access  = tokens["access_token"]
        refresh = tokens["refresh_token"]

        # Logout
        await client.post(LOGOUT_URL, headers={
            "Authorization": f"Bearer {access}",
        }, json={"refresh_token": refresh})

        # Attacker tries same token multiple times
        for attempt in range(3):
            resp = await client.post(REFRESH_URL, json={"refresh_token": refresh})
            assert resp.status_code in (401, 403), (
                f"Replay attempt {attempt+1} succeeded — blacklist not enforced!"
            )

    @pytest.mark.asyncio
    async def test_token_rotation_old_rejected_new_works(
        self, client: AsyncClient, free_plan
    ):
        tokens = await register_and_login(client, "rotation", free_plan)
        orig_refresh = tokens["refresh_token"]

        # Rotate: get new token pair
        rotate_resp = await client.post(REFRESH_URL, json={"refresh_token": orig_refresh})
        assert rotate_resp.status_code == 200
        new_tokens = rotate_resp.json()

        # Old token must be blacklisted now
        old_retry = await client.post(REFRESH_URL, json={"refresh_token": orig_refresh})
        assert old_retry.status_code in (401, 403), (
            "Old refresh token accepted after rotation — GAP-003 NOT fixed!"
        )

        # New token must still work
        new_access = new_tokens["access_token"]
        me_resp = await client.get(ME_URL, headers={
            "Authorization": f"Bearer {new_access}",
        })
        assert me_resp.status_code == 200


# ════════════════════════════════════════════════════
# GAP-003-B: Multi-session isolation
# ════════════════════════════════════════════════════
class TestMultiSessionIsolation:

    @pytest.mark.asyncio
    async def test_logout_one_session_does_not_invalidate_other(
        self, client: AsyncClient, free_plan
    ):
        """
        User logged in on Device A and Device B.
        Logging out Device A must NOT invalidate Device B's token.
        """
        # Register once
        payload = fresh_user("multi_sess")
        await client.post(REGISTER_URL, json=payload)

        # Login from "Device A"
        resp_a = await client.post(LOGIN_URL, json={
            "email": payload["email"], "password": payload["password"],
        })
        tokens_a = resp_a.json()

        # Login from "Device B"
        resp_b = await client.post(LOGIN_URL, json={
            "email": payload["email"], "password": payload["password"],
        })
        tokens_b = resp_b.json()

        # Device A logs out
        await client.post(LOGOUT_URL, headers={
            "Authorization": f"Bearer {tokens_a['access_token']}",
        }, json={"refresh_token": tokens_a["refresh_token"]})

        # Device B refresh must still work
        refresh_b = await client.post(REFRESH_URL, json={
            "refresh_token": tokens_b["refresh_token"],
        })
        assert refresh_b.status_code == 200, (
            "Device B session was invalidated by Device A logout — session isolation broken!"
        )


# ════════════════════════════════════════════════════
# GAP-003-C: Invalid/malformed token fast rejection
# ════════════════════════════════════════════════════
class TestMalformedRefreshTokenRejection:

    @pytest.mark.asyncio
    async def test_invalid_token_string_rejected(self, client: AsyncClient, free_plan):
        resp = await client.post(REFRESH_URL, json={"refresh_token": "notarealtoken"})
        assert resp.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_empty_token_rejected(self, client: AsyncClient, free_plan):
        resp = await client.post(REFRESH_URL, json={"refresh_token": ""})
        assert resp.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_missing_token_field_rejected(self, client: AsyncClient, free_plan):
        resp = await client.post(REFRESH_URL, json={})
        assert resp.status_code == 422
