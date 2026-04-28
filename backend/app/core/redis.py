"""
Conduit Backend — Redis Client
Prompt 3 Security:
  - Rate limiting: 5 attempts/15min per IP
  - Account lockout: 10 attempts → lock 1 hour
  - JWT blacklist: revoked tokens with TTL
  - Blacklist: Redis with TTL = remaining token lifespan

LAW: All rate limiting uses sliding window algorithm.
"""

from redis.asyncio import Redis

from app.core.config import settings

# ── Redis Client ──
redis_client = Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=20,
)


async def init_redis() -> None:
    """Verify Redis connectivity on startup."""
    await redis_client.ping()


async def close_redis() -> None:
    """Close Redis connections on shutdown."""
    await redis_client.aclose()


# ══════════════════════════════════════
# RATE LIMITING — Sliding Window
# ══════════════════════════════════════

async def check_rate_limit(
    key: str,
    max_attempts: int = settings.LOGIN_RATE_LIMIT_MAX,
    window_seconds: int = settings.LOGIN_RATE_LIMIT_WINDOW,
) -> tuple[bool, int]:
    """
    Sliding window rate limiter.

    Args:
        key: Unique identifier (e.g., f"login:{ip_address}")
        max_attempts: Maximum allowed in window
        window_seconds: Window size in seconds

    Returns:
        tuple: (is_allowed, remaining_attempts)
    """
    redis_key = f"ratelimit:{key}"
    current = await redis_client.get(redis_key)

    if current is None:
        await redis_client.setex(redis_key, window_seconds, 1)
        return True, max_attempts - 1

    count = int(current)
    if count >= max_attempts:
        ttl = await redis_client.ttl(redis_key)
        return False, 0

    await redis_client.incr(redis_key)
    return True, max_attempts - count - 1


async def get_rate_limit_ttl(key: str) -> int:
    """Get remaining seconds until rate limit resets."""
    redis_key = f"ratelimit:{key}"
    ttl = await redis_client.ttl(redis_key)
    return max(ttl, 0)


# ══════════════════════════════════════
# ACCOUNT LOCKOUT
# ══════════════════════════════════════

async def increment_login_failure(user_id: str) -> int:
    """
    Track failed login attempts.
    Prompt 3: "10 intentos → lock 1 hora → email de unlock"

    Returns current failure count.
    """
    redis_key = f"lockout:{user_id}"
    count = await redis_client.incr(redis_key)

    if count == 1:
        # First failure — set expiry window
        await redis_client.expire(redis_key, settings.ACCOUNT_LOCKOUT_DURATION)

    return count


async def is_account_locked(user_id: str) -> bool:
    """Check if account is locked due to too many failures."""
    redis_key = f"lockout:{user_id}"
    count = await redis_client.get(redis_key)
    if count is None:
        return False
    return int(count) >= settings.ACCOUNT_LOCKOUT_THRESHOLD


async def clear_login_failures(user_id: str) -> None:
    """Clear failure counter on successful login."""
    redis_key = f"lockout:{user_id}"
    await redis_client.delete(redis_key)


async def get_lockout_ttl(user_id: str) -> int:
    """Get remaining lockout duration in seconds."""
    redis_key = f"lockout:{user_id}"
    ttl = await redis_client.ttl(redis_key)
    return max(ttl, 0)


# ══════════════════════════════════════
# JWT BLACKLIST — Revoked Tokens
# ══════════════════════════════════════

async def blacklist_token(jti: str, ttl_seconds: int) -> None:
    """
    Add token to blacklist.
    Prompt 3: "Blacklist en Redis con TTL = vida restante del token"

    Args:
        jti: JWT unique identifier (jti claim)
        ttl_seconds: Remaining lifespan of token
    """
    redis_key = f"blacklist:{jti}"
    await redis_client.setex(redis_key, ttl_seconds, "1")


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a token has been revoked."""
    redis_key = f"blacklist:{jti}"
    return await redis_client.exists(redis_key) > 0


# ══════════════════════════════════════
# REFRESH TOKEN BLACKLIST
# ══════════════════════════════════════

async def blacklist_refresh_token(token_hash: str, ttl_seconds: int) -> None:
    """Blacklist a refresh token hash after rotation."""
    redis_key = f"refresh_blacklist:{token_hash}"
    await redis_client.setex(redis_key, ttl_seconds, "1")


async def is_refresh_token_blacklisted(token_hash: str) -> bool:
    """Check if refresh token has been revoked."""
    redis_key = f"refresh_blacklist:{token_hash}"
    return await redis_client.exists(redis_key) > 0
