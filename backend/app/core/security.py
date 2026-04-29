"""
Conduit Backend — Core Security Module
Prompt 3 Security:
  - JWT RS256 (RSA 2048 keypair)
  - Bcrypt cost 12
  - Refresh token rotation
  - Cryptographic OTP generation

LAW: Never leak timing information in password comparison.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── Password Hashing ──
# Prompt 3: "Bcrypt cost 12"
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)


def hash_password(plain: str) -> str:
    """Hash password with bcrypt. Cost factor from settings."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Timing-safe password verification."""
    return pwd_context.verify(plain, hashed)


# ── JWT RS256 Token Management ──

def _get_private_key() -> str:
    """
    Get RSA private key for signing.
    LAW: In production, missing key = hard failure. No silent downgrade.
    """
    key = settings.jwt_private_key
    if not key:
        if settings.is_production:
            msg = (
                "FATAL: JWT_PRIVATE_KEY_PATH not configured or file missing. "
                "Cannot start in production without RSA key."
            )
            raise RuntimeError(msg)
        # Dev-only fallback: HS256 with APP_SECRET_KEY
        return settings.APP_SECRET_KEY
    return key


def _get_public_key() -> str:
    """
    Get RSA public key for verification.
    LAW: In production, missing key = hard failure.
    """
    key = settings.jwt_public_key
    if not key:
        if settings.is_production:
            msg = (
                "FATAL: JWT_PUBLIC_KEY_PATH not configured or file missing. "
                "Cannot verify tokens in production without RSA key."
            )
            raise RuntimeError(msg)
        return settings.APP_SECRET_KEY
    return key


def _get_algorithm() -> str:
    """RS256 when RSA key present, HS256 dev-only fallback."""
    if settings.jwt_private_key:
        return "RS256"
    return "HS256"


def create_access_token(
    user_id: uuid.UUID,
    org_id: uuid.UUID | None = None,
    roles: list[str] | None = None,
    extra_claims: dict | None = None,
) -> str:
    """
    Create short-lived access token.
    Prompt 3: "access (15min)"

    Claims:
    - sub: user_id
    - org: org_id (current active org)
    - roles: list of role strings
    - exp: expiration
    - iat: issued at
    - jti: unique token ID
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "org": str(org_id) if org_id else None,
        "roles": roles or [],
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        _get_private_key(),
        algorithm=_get_algorithm(),
    )


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str]:
    """
    Create long-lived refresh token.
    Prompt 3: "refresh (30 días)"
    Prompt 3: "Refresh tokens rotativos — cada uso genera nuevo token"

    Returns:
        tuple: (raw_token, token_hash) — store hash in DB, return raw to client
    """
    raw_token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def hash_refresh_token(raw_token: str) -> str:
    """Hash a raw refresh token for DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def verify_access_token(token: str) -> dict:
    """
    Decode and validate access token.

    Returns decoded claims dict.
    Raises JWTError on invalid/expired token.
    """
    try:
        payload = jwt.decode(
            token,
            _get_public_key(),
            algorithms=[_get_algorithm()],
        )

        if payload.get("type") != "access":
            msg = "Invalid token type"
            raise JWTError(msg)

        return payload

    except JWTError:
        raise


def generate_invitation_token() -> str:
    """
    Generate cryptographically secure invitation/OTP token.
    Prompt 3: OTP for password reset and invitations.
    """
    return secrets.token_urlsafe(48)


def generate_password_reset_token() -> str:
    """Generate cryptographically secure password reset token."""
    return secrets.token_urlsafe(48)
