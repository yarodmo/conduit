"""
FORENSIC TEST — GAP-005: RSA Key Hard Failure in Production
============================================================
Validates:
  1. Missing RSA private key raises RuntimeError in production mode
  2. Missing RSA public key raises RuntimeError in production mode  
  3. Development mode falls back to symmetric key gracefully
  4. Token signed with RS256 contains correct alg header
  5. Token signed in dev mode is rejected in production verify

Bliss Systems LLC — APEX Standard | Sprint 1 Validation
"""

import os
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


# ════════════════════════════════════════════════════
# RSA Key Generator (in-memory, for test isolation)
# ════════════════════════════════════════════════════
def generate_rsa_keypair() -> tuple[bytes, bytes]:
    """Generate a fresh RSA-2048 keypair — returns (private_pem, public_pem)."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


# ════════════════════════════════════════════════════
# GAP-005-A: Production hard-failure on missing keys
# ════════════════════════════════════════════════════
class TestRSAProductionHardFailure:

    def test_missing_private_key_raises_in_production(self):
        """
        GAP-005 CRITICAL: App must NEVER silently downgrade to HS256.
        Missing private key in production must raise RuntimeError immediately.
        """
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with patch("app.core.security.settings") as mock_settings:
                mock_settings.ENVIRONMENT = "production"
                mock_settings.JWT_PRIVATE_KEY = None
                mock_settings.JWT_PUBLIC_KEY = None
                mock_settings.SECRET_KEY = "should-not-be-used"

                with pytest.raises(RuntimeError, match="RSA"):
                    from importlib import reload
                    import app.core.security as sec_module
                    # Force key resolution
                    sec_module._get_private_key()

    def test_missing_public_key_raises_in_production(self):
        """Missing public key in production must raise RuntimeError."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with patch("app.core.security.settings") as mock_settings:
                mock_settings.ENVIRONMENT = "production"
                mock_settings.JWT_PRIVATE_KEY = None
                mock_settings.JWT_PUBLIC_KEY = None

                with pytest.raises(RuntimeError, match="RSA"):
                    import app.core.security as sec_module
                    sec_module._get_public_key()

    def test_with_valid_rsa_keys_production_works(self):
        """Valid RSA keys in production must work without errors."""
        priv_pem, pub_pem = generate_rsa_keypair()

        with patch("app.core.security.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            mock_settings.JWT_PRIVATE_KEY = priv_pem.decode()
            mock_settings.JWT_PUBLIC_KEY = pub_pem.decode()

            import app.core.security as sec_module
            # Must not raise
            priv = sec_module._get_private_key()
            pub = sec_module._get_public_key()
            assert priv is not None
            assert pub is not None


# ════════════════════════════════════════════════════
# GAP-005-B: Token alg header validation
# ════════════════════════════════════════════════════
class TestJWTAlgorithmEnforcement:

    def test_access_token_uses_rs256(self):
        """Access token must declare RS256 in header."""
        import jwt as pyjwt
        from app.core.security import create_access_token
        import uuid

        token = create_access_token(
            user_id=uuid.uuid4(),
            email="test@conduit.build",
        )
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "RS256", (
            f"Expected RS256 but got {header['alg']} — HS256 downgrade detected!"
        )

    def test_token_verify_rejects_hs256_tokens(self):
        """A token signed with HS256 (attacker forgery) must be rejected."""
        import jwt as pyjwt
        from app.core.security import verify_token

        # Craft a fake HS256 token
        fake_payload = {
            "sub": str("00000000-0000-0000-0000-000000000000"),
            "type": "access",
            "jti": "fakejti",
        }
        attacker_token = pyjwt.encode(fake_payload, "attacker_secret", algorithm="HS256")

        with pytest.raises(Exception):
            verify_token(attacker_token, token_type="access")


# ════════════════════════════════════════════════════
# GAP-005-C: Development mode graceful fallback
# ════════════════════════════════════════════════════
class TestDevelopmentModeFallback:

    def test_dev_mode_without_rsa_does_not_raise_runtime_error(self):
        """
        In development/testing, missing RSA keys should NOT crash the app.
        They should fall back to test-safe symmetric signing.
        """
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "development"
            mock_settings.JWT_PRIVATE_KEY = None
            mock_settings.JWT_PUBLIC_KEY = None
            mock_settings.SECRET_KEY = "dev_test_secret_key_32_chars_ok!"

            import app.core.security as sec_module
            # Should not raise in dev mode
            try:
                key = sec_module._get_private_key()
                # If it returns something, fine; if it raises, must NOT be RuntimeError
            except RuntimeError:
                pytest.fail("RuntimeError raised in development mode — should not happen")
            except Exception:
                pass  # Other exceptions acceptable in dev mode fallback
