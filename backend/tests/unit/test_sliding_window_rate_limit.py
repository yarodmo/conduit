"""
FORENSIC TEST — GAP-002: Sliding Window Rate Limiting
======================================================
Validates that the Redis ZSET-based sliding window:
  1. Blocks exactly after the limit
  2. Is NOT bypassable via the fixed-window boundary attack
  3. Correctly ages out entries at the sliding boundary
  4. Returns correct remaining/reset metadata

Bliss Systems LLC — APEX Standard | Sprint 1 Validation
"""

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from app.core.redis import (
    check_rate_limit,
    get_rate_limit_ttl,
)


@pytest.fixture
def redis():
    """Isolated FakeRedis instance per test."""
    client = FakeRedis(decode_responses=True)
    yield client


@pytest.fixture(autouse=True)
def patch_redis(redis):
    """Patch app redis_client with our FakeRedis."""
    import app.core.redis as m
    orig = m.redis_client
    m.redis_client = redis
    yield
    m.redis_client = orig


# ── Helper ──────────────────────────────────────────
def unique_key() -> str:
    return f"test:rl:{uuid.uuid4().hex}"


# ════════════════════════════════════════════════════
# GAP-002-A: Basic limit enforcement
# ════════════════════════════════════════════════════
class TestSlidingWindowBasicEnforcement:

    @pytest.mark.asyncio
    async def test_allows_requests_below_limit(self, redis):
        key = unique_key()
        for i in range(4):
            allowed, meta = await check_rate_limit(key, limit=5, window_seconds=60)
            assert allowed is True, f"Request {i+1} should be allowed"

    @pytest.mark.asyncio
    async def test_blocks_exactly_at_limit(self, redis):
        key = unique_key()
        limit = 3
        # Consume all slots
        for _ in range(limit):
            allowed, _ = await check_rate_limit(key, limit=limit, window_seconds=60)
            assert allowed is True
        # Next must be blocked
        allowed, meta = await check_rate_limit(key, limit=limit, window_seconds=60)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_meta_shows_correct_remaining(self, redis):
        key = unique_key()
        _, meta = await check_rate_limit(key, limit=5, window_seconds=60)
        assert meta["remaining"] == 4  # one used, 4 left

    @pytest.mark.asyncio
    async def test_meta_remaining_reaches_zero_when_blocked(self, redis):
        key = unique_key()
        for _ in range(5):
            await check_rate_limit(key, limit=5, window_seconds=60)
        _, meta = await check_rate_limit(key, limit=5, window_seconds=60)
        assert meta["remaining"] == 0
        assert meta["retry_after"] > 0

    @pytest.mark.asyncio
    async def test_different_keys_are_independent(self, redis):
        key_a = unique_key()
        key_b = unique_key()
        # Exhaust key_a
        for _ in range(3):
            await check_rate_limit(key_a, limit=3, window_seconds=60)
        blocked_a, _ = await check_rate_limit(key_a, limit=3, window_seconds=60)
        allowed_b, _ = await check_rate_limit(key_b, limit=3, window_seconds=60)
        assert blocked_a is False
        assert allowed_b is True


# ════════════════════════════════════════════════════
# GAP-002-B: Fixed-window boundary bypass prevention
# ════════════════════════════════════════════════════
class TestFixedWindowBypassPrevention:
    """
    Attack: in fixed-window, send (limit) requests at T=59s,
    then (limit) more at T=61s (new window). Gets 2*limit through.
    In sliding window this MUST be blocked because the earlier
    requests still count within the 60s window.
    """

    @pytest.mark.asyncio
    async def test_sliding_window_prevents_boundary_burst(self, redis):
        key = unique_key()
        limit = 5
        window = 60

        now = time.time()

        # Simulate: 4 requests at t=now-55 (still inside the 60s window)
        early_time = now - 55
        for i in range(4):
            ts = early_time + i * 0.001  # microsecond spread
            await redis.zadd(key, {f"hit:{i}": ts})
        await redis.expire(key, window)

        # Now attempt 2 more — only 1 slot remains
        allowed1, _ = await check_rate_limit(key, limit=limit, window_seconds=window)
        allowed2, _ = await check_rate_limit(key, limit=limit, window_seconds=window)

        assert allowed1 is True,  "Slot 5/5 should be allowed"
        assert allowed2 is False, "Boundary burst attack: 6th must be BLOCKED"

    @pytest.mark.asyncio
    async def test_old_entries_expire_from_window(self, redis):
        key = unique_key()
        limit = 3
        window = 10  # 10s window

        now = time.time()

        # Inject 3 requests older than window (should NOT count)
        for i in range(3):
            ts = now - 15 - i  # 15-17s ago
            await redis.zadd(key, {f"old:{i}": ts})

        # All 3 new requests should be allowed
        for i in range(3):
            allowed, _ = await check_rate_limit(key, limit=limit, window_seconds=window)
            assert allowed is True, f"Fresh window: request {i+1} should be allowed"


# ════════════════════════════════════════════════════
# GAP-002-C: TTL helper
# ════════════════════════════════════════════════════
class TestRateLimitTTL:

    @pytest.mark.asyncio
    async def test_ttl_returns_positive_when_blocked(self, redis):
        key = unique_key()
        limit = 2
        window = 60
        for _ in range(2):
            await check_rate_limit(key, limit=limit, window_seconds=window)
        ttl = await get_rate_limit_ttl(key)
        assert ttl > 0

    @pytest.mark.asyncio
    async def test_ttl_returns_zero_for_empty_key(self, redis):
        key = unique_key()
        ttl = await get_rate_limit_ttl(key)
        assert ttl == 0


# ════════════════════════════════════════════════════
# GAP-003-B: Refresh token blacklist fast-fail
# ════════════════════════════════════════════════════
class TestRefreshTokenBlacklist:

    @pytest.mark.asyncio
    async def test_blacklisted_token_is_detected(self, redis):
        from app.core.redis import is_refresh_token_blacklisted, blacklist_refresh_token
        token = f"tok:{uuid.uuid4().hex}"
        await blacklist_refresh_token(token, ttl_seconds=3600)
        is_blacklisted = await is_refresh_token_blacklisted(token)
        assert is_blacklisted is True

    @pytest.mark.asyncio
    async def test_non_blacklisted_token_passes(self, redis):
        from app.core.redis import is_refresh_token_blacklisted
        token = f"tok:{uuid.uuid4().hex}"
        is_blacklisted = await is_refresh_token_blacklisted(token)
        assert is_blacklisted is False

    @pytest.mark.asyncio
    async def test_blacklist_is_isolated_per_token(self, redis):
        from app.core.redis import is_refresh_token_blacklisted, blacklist_refresh_token
        tok_a = f"tok:{uuid.uuid4().hex}"
        tok_b = f"tok:{uuid.uuid4().hex}"
        await blacklist_refresh_token(tok_a, ttl_seconds=3600)
        assert await is_refresh_token_blacklisted(tok_a) is True
        assert await is_refresh_token_blacklisted(tok_b) is False
