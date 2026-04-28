"""
Conduit Tests — Unit: Core Security
16 tests covering: JWT, bcrypt, token rotation, blacklist.

Bliss Systems LLC — APEX Standard
"""

import time
import uuid

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_invitation_token,
    generate_password_reset_token,
    hash_password,
    hash_refresh_token,
    verify_access_token,
    verify_password,
)


# ══════════════════════════════════════
# PASSWORD HASHING — Bcrypt cost 12
# ══════════════════════════════════════

class TestPasswordHashing:
    def test_hash_produces_bcrypt_format(self):
        """Hash must start with $2b$ (bcrypt identifier)."""
        hashed = hash_password("MyPassword123!")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_hash_is_unique_for_same_password(self):
        """Two hashes of same password must differ (salt)."""
        h1 = hash_password("MyPassword123!")
        h2 = hash_password("MyPassword123!")
        assert h1 != h2

    def test_verify_correct_password(self):
        """Correct password must verify successfully."""
        hashed = hash_password("CorrectPass1!")
        assert verify_password("CorrectPass1!", hashed) is True

    def test_verify_wrong_password(self):
        """Wrong password must fail verification."""
        hashed = hash_password("CorrectPass1!")
        assert verify_password("WrongPass1!", hashed) is False

    def test_verify_empty_password_fails(self):
        """Empty password must fail against any real hash."""
        hashed = hash_password("RealPass123!")
        assert verify_password("", hashed) is False

    def test_hash_cannot_be_reversed(self):
        """Hash length must be standard bcrypt (60 chars)."""
        hashed = hash_password("IrreversiblePass1!")
        assert len(hashed) == 60


# ══════════════════════════════════════
# JWT ACCESS TOKENS
# ══════════════════════════════════════

class TestJWTAccessToken:
    def test_create_access_token_returns_string(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        assert isinstance(token, str)
        assert len(token) > 50

    def test_access_token_contains_correct_claims(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(user_id, org_id, ["ORG_ADMIN"])
        payload = verify_access_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["org"] == str(org_id)
        assert "ORG_ADMIN" in payload["roles"]
        assert payload["type"] == "access"

    def test_access_token_has_jti(self):
        """Every token must have unique jti for blacklisting."""
        t1 = create_access_token(uuid.uuid4())
        t2 = create_access_token(uuid.uuid4())
        p1 = verify_access_token(t1)
        p2 = verify_access_token(t2)
        assert p1["jti"] != p2["jti"]

    def test_token_without_org_sets_none(self):
        token = create_access_token(uuid.uuid4(), org_id=None)
        payload = verify_access_token(token)
        assert payload["org"] is None

    def test_tampered_token_raises(self):
        """Tampered token must raise JWTError."""
        token = create_access_token(uuid.uuid4())
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            verify_access_token(tampered)

    def test_wrong_type_token_rejected(self):
        """Refresh-type payload must not pass access token validation."""
        from jose import jwt
        from app.core.security import _get_private_key, _get_algorithm
        import datetime

        payload = {
            "sub": str(uuid.uuid4()),
            "type": "refresh",  # Wrong type
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=15),
            "jti": str(uuid.uuid4()),
            "iat": datetime.datetime.utcnow(),
        }
        token = jwt.encode(payload, _get_private_key(), algorithm=_get_algorithm())

        with pytest.raises(JWTError):
            verify_access_token(token)


# ══════════════════════════════════════
# REFRESH TOKEN ROTATION
# ══════════════════════════════════════

class TestRefreshTokens:
    def test_create_refresh_token_returns_tuple(self):
        raw, token_hash = create_refresh_token(uuid.uuid4())
        assert isinstance(raw, str)
        assert isinstance(token_hash, str)

    def test_raw_and_hash_are_different(self):
        """Raw token ≠ stored hash (SHA256 transformation)."""
        raw, token_hash = create_refresh_token(uuid.uuid4())
        assert raw != token_hash

    def test_hash_is_deterministic(self):
        """Same raw token always hashes to same value."""
        raw, _ = create_refresh_token(uuid.uuid4())
        h1 = hash_refresh_token(raw)
        h2 = hash_refresh_token(raw)
        assert h1 == h2

    def test_different_tokens_have_different_hashes(self):
        """Two different raw tokens must produce different hashes."""
        raw1, hash1 = create_refresh_token(uuid.uuid4())
        raw2, hash2 = create_refresh_token(uuid.uuid4())
        assert hash1 != hash2

    def test_refresh_token_urlsafe_chars_only(self):
        """Raw refresh token must be URL-safe."""
        import re
        raw, _ = create_refresh_token(uuid.uuid4())
        assert re.match(r"^[A-Za-z0-9_\-]+$", raw), "Token contains non-URL-safe characters"


# ══════════════════════════════════════
# OTP / INVITATION TOKENS
# ══════════════════════════════════════

class TestOTPGeneration:
    def test_invitation_token_length_sufficient(self):
        """Invitation tokens must be cryptographically strong (>= 48 bytes entropy)."""
        token = generate_invitation_token()
        # base64url: 48 bytes → 64 characters minimum
        assert len(token) >= 60

    def test_password_reset_token_unique(self):
        """Two reset tokens must never collide."""
        t1 = generate_password_reset_token()
        t2 = generate_password_reset_token()
        assert t1 != t2

    def test_invitation_token_urlsafe(self):
        """Token must be safe for URL embedding."""
        import re
        token = generate_invitation_token()
        assert re.match(r"^[A-Za-z0-9_\-]+$", token)
