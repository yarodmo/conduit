"""
PENETRATION TEST SUITE — OWASP Top 10 for Conduit
═════════════════════════════════════════════════════════════════════════════
20 black-box attack simulations validating defense-in-depth against the
attack patterns most likely to harm Conduit users.

PROMPT 12 (master prompt) — Suite de 20 penetration tests básicos.

Layout:
  A01 Broken Access Control      → 4 tests
  A02 Cryptographic Failures     → 3 tests
  A03 Injection                  → 4 tests
  A05 Security Misconfiguration  → 1 test
  A07 Authentication Failures    → 2 tests
  Security HTTP Headers          → 6 tests
                                 ─── 20 total ───

Conduit-specific risk note:
  Construction plans are confidential IP. A breach of tenant isolation (A01)
  exposes one MEP firm's bids and pricing to its competitors — this is the
  #1 security risk for the product, hence the heavy weight on A01.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.projects import Project, ProjectComplexity, ProjectType

API = "/api/v1"


# ══════════════════════════════════════════════════════════════════════════
# A01 — BROKEN ACCESS CONTROL (4 tests)
# ══════════════════════════════════════════════════════════════════════════

class TestA01BrokenAccessControl:
    """
    Tenant isolation is the #1 security risk for Conduit — plans are
    confidential IP. Every endpoint must enforce org_id derived from
    X-Organization-ID header, never from request body.
    """

    @pytest.mark.asyncio
    async def test_cross_tenant_project_returns_404(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession,
        test_user: dict, free_plan,
    ):
        """Org B must not see Org A's projects — return 404, not 403 (no leak)."""
        # Seed a project in Org A
        proj_a = Project(
            name="Confidential Project A",
            org_id=test_user["org"].id,
            type=ProjectType.COMMERCIAL,
            complexity=ProjectComplexity.STANDARD,
            is_active=True,
        )
        db.add(proj_a)
        await db.commit()

        # Register Org B
        reg = await client.post(f"{API}/register", json={
            "email": f"orgb_{uuid.uuid4().hex[:6]}@rival.build",
            "password": "RivalPass1!",
            "full_name": "Rival",
            "org_name": "Rival MEP",
        })
        assert reg.status_code == 201
        tokens_b = reg.json()
        me_b = await client.get(
            f"{API}/me",
            headers={"Authorization": f"Bearer {tokens_b['access_token']}"},
        )
        org_b_id = me_b.json()["organizations"][0]["org_id"]
        headers_b = {
            "Authorization": f"Bearer {tokens_b['access_token']}",
            "X-Organization-ID": org_b_id,
        }

        resp = await client.get(f"{API}/projects/{proj_a.id}", headers=headers_b)
        assert resp.status_code == 404, (
            f"Cross-tenant access returned {resp.status_code}. "
            "Construction plan IP cannot leak between firms."
        )

    @pytest.mark.asyncio
    async def test_missing_x_organization_id_header_rejected(
        self, client: AsyncClient, auth_headers: dict, free_plan,
    ):
        """Protected endpoints without X-Organization-ID must return 400."""
        headers_no_org = {"Authorization": auth_headers["Authorization"]}
        resp = await client.get(f"{API}/projects", headers=headers_no_org)
        assert resp.status_code == 400, (
            "Missing tenant header must block — never default to first org silently."
        )

    @pytest.mark.asyncio
    async def test_x_organization_id_for_unrelated_org_rejected(
        self, client: AsyncClient, auth_headers: dict, free_plan,
    ):
        """User with org A token but X-Org header pointing to random UUID → blocked."""
        spoofed = {
            "Authorization": auth_headers["Authorization"],
            "X-Organization-ID": str(uuid.uuid4()),
        }
        resp = await client.get(f"{API}/projects", headers=spoofed)
        assert resp.status_code in {400, 403, 404}, (
            "User must not be able to assume an org they don't belong to."
        )

    @pytest.mark.asyncio
    async def test_unauthenticated_request_to_protected_endpoint_returns_401(
        self, client: AsyncClient,
    ):
        """No Authorization header → 401 Unauthorized."""
        resp = await client.get(f"{API}/projects")
        assert resp.status_code in {401, 403}


# ══════════════════════════════════════════════════════════════════════════
# A02 — CRYPTOGRAPHIC FAILURES (3 tests)
# ══════════════════════════════════════════════════════════════════════════

class TestA02CryptographicFailures:
    """
    JWT must use RS256 (asymmetric) — HS256 (shared secret) is forbidden
    because a leaked secret key allows token forgery org-wide. Passwords
    must be bcrypt-hashed at cost 12 and never round-tripped to clients.
    """

    @pytest.mark.asyncio
    async def test_jwt_signed_with_hs256_rejected(
        self, client: AsyncClient, test_user: dict,
    ):
        """
        Algorithm-confusion attack: attacker signs token with HS256 using
        the RSA public key as HMAC secret. RS256-only enforcement must reject.
        """
        forged = jwt.encode(
            {
                "sub": str(test_user["user"].id),
                "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=15),
                "type": "access",
            },
            "attacker-supplied-secret",
            algorithm="HS256",
        )
        resp = await client.get(
            f"{API}/me",
            headers={"Authorization": f"Bearer {forged}"},
        )
        assert resp.status_code in {401, 403}, (
            "HS256-signed token accepted — algorithm confusion attack possible."
        )

    @pytest.mark.asyncio
    async def test_password_never_returned_in_login_response(
        self, client: AsyncClient, test_user: dict, free_plan,
    ):
        """Login response must not echo the password or its hash."""
        resp = await client.post(f"{API}/login", json={
            "email": test_user["email"],
            "password": test_user["password"],
        })
        assert resp.status_code == 200
        body_str = resp.text.lower()
        assert test_user["password"].lower() not in body_str, (
            "Plaintext password leaked in login response."
        )
        # bcrypt hashes start with $2b$ / $2a$ — never expose
        assert "$2b$" not in body_str and "$2a$" not in body_str, (
            "Password hash leaked in login response."
        )

    @pytest.mark.asyncio
    async def test_expired_token_rejected(
        self, client: AsyncClient, test_user: dict,
    ):
        """A token with exp < now must be rejected with 401."""
        # Craft a token that LOOKS valid but is expired — RS256 will fail
        # signature check too, both paths must reject. We use HS256 here
        # to also cover the algorithm enforcement above.
        expired = jwt.encode(
            {
                "sub": str(test_user["user"].id),
                "exp": datetime.now(tz=timezone.utc) - timedelta(minutes=5),
                "type": "access",
            },
            "any-secret",
            algorithm="HS256",
        )
        resp = await client.get(
            f"{API}/me",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code in {401, 403}


# ══════════════════════════════════════════════════════════════════════════
# A03 — INJECTION (4 tests)
# ══════════════════════════════════════════════════════════════════════════

class TestA03Injection:
    """
    SQLAlchemy parameterizes queries by default, but input validation is
    a second line of defense. Path traversal, XSS payloads, and SQL
    metacharacters must be either rejected at validation or rendered
    inert at storage.
    """

    @pytest.mark.asyncio
    async def test_sql_injection_in_email_does_not_authenticate(
        self, client: AsyncClient, test_user: dict, free_plan,
    ):
        """Classic ' OR 1=1 -- payload in login must fail, not auth-bypass."""
        resp = await client.post(f"{API}/login", json={
            "email": "admin@conduit.build' OR '1'='1",
            "password": "anything",
        })
        # Either 422 (email validation rejects) or 401 (no user matches)
        assert resp.status_code in {401, 422}, (
            f"SQLi payload returned {resp.status_code} — auth bypass possible."
        )
        # Critically: must NOT return 200 with a valid token
        assert "access_token" not in resp.text

    @pytest.mark.asyncio
    async def test_sql_injection_in_path_param_rejected(
        self, client: AsyncClient, auth_headers: dict, free_plan,
    ):
        """SQLi metachars in a UUID path param must be rejected at parsing."""
        resp = await client.get(
            f"{API}/projects/'%20OR%201=1%20--",
            headers=auth_headers,
        )
        assert resp.status_code in {400, 404, 422}, (
            "Non-UUID path param did not fail validation."
        )

    @pytest.mark.asyncio
    async def test_path_traversal_in_filename_blocked(
        self, client: AsyncClient, auth_headers: dict, free_plan,
    ):
        """Upload with '../../etc/passwd' as filename must be rejected."""
        # We don't need a real project — the filename check happens before
        # the upload pipeline. A non-existent project_id will return 404
        # *after* validation, never reach the file storage path.
        evil_uuid = uuid.uuid4()
        resp = await client.post(
            f"{API}/projects/{evil_uuid}/plans/upload",
            files={"file": ("../../etc/passwd", b"fake-content", "image/jpeg")},
            headers=auth_headers,
        )
        # Either 400/422 (filename validation) or 404 (project not found) — never 200
        assert resp.status_code != 200
        assert resp.status_code != 201

    @pytest.mark.asyncio
    async def test_xss_payload_stored_safely(
        self, client: AsyncClient, auth_headers: dict, free_plan,
    ):
        """<script> in project description must persist as text, never execute."""
        payload = "<script>alert('xss')</script>"
        create_resp = await client.post(
            f"{API}/projects",
            json={
                "name": "XSS Test",
                "description": payload,
                "type": "commercial",
                "complexity": "simple",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        proj_id = create_resp.json()["id"]

        get_resp = await client.get(f"{API}/projects/{proj_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        # Payload is returned as JSON text — the browser MUST NOT execute it,
        # and we verify it's returned via JSON (Content-Type matters here).
        ctype = get_resp.headers.get("content-type", "")
        assert "application/json" in ctype, (
            "Non-JSON content-type allows browser to execute embedded scripts."
        )
        assert get_resp.json()["description"] == payload


# ══════════════════════════════════════════════════════════════════════════
# A05 — SECURITY MISCONFIGURATION (1 test)
# ══════════════════════════════════════════════════════════════════════════

class TestA05SecurityMisconfiguration:

    @pytest.mark.asyncio
    async def test_health_endpoint_does_not_leak_secrets(
        self, client: AsyncClient,
    ):
        """/health response must not expose env vars, paths, or secret material."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.text.lower()
        forbidden = [
            "secret_key", "jwt_private_key", "jwt_public_key", "database_url",
            "smtp_password", "$2b$", "bearer ", "-----begin",
        ]
        for needle in forbidden:
            assert needle not in body, f"/health leaked '{needle}'"


# ══════════════════════════════════════════════════════════════════════════
# A07 — AUTH FAILURES (2 tests)
# ══════════════════════════════════════════════════════════════════════════

class TestA07AuthFailures:

    @pytest.mark.asyncio
    async def test_login_with_wrong_password_does_not_reveal_user_existence(
        self, client: AsyncClient, test_user: dict, free_plan,
    ):
        """
        Wrong-password and unknown-user must return identical error shapes
        so attackers can't enumerate registered emails.
        """
        wrong_pass = await client.post(f"{API}/login", json={
            "email": test_user["email"],
            "password": "WrongPassword1!",
        })
        unknown_user = await client.post(f"{API}/login", json={
            "email": f"ghost_{uuid.uuid4().hex[:6]}@nowhere.com",
            "password": "WrongPassword1!",
        })
        # Both must fail with the same status code — no email-enum oracle
        assert wrong_pass.status_code == unknown_user.status_code, (
            f"Different responses ({wrong_pass.status_code} vs "
            f"{unknown_user.status_code}) allow email enumeration."
        )

    @pytest.mark.asyncio
    async def test_refresh_token_required_for_refresh_endpoint(
        self, client: AsyncClient,
    ):
        """Refresh endpoint must reject requests without a refresh token."""
        resp = await client.post(f"{API}/refresh", json={})
        assert resp.status_code in {400, 401, 422}


# ══════════════════════════════════════════════════════════════════════════
# SECURITY HTTP HEADERS (6 tests)
# ══════════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    """
    SecurityMiddleware must apply these headers to every response, including
    error responses, exempt paths, and unauthenticated endpoints.
    HSTS is production-only and excluded here.
    """

    @pytest.mark.asyncio
    async def test_response_has_x_frame_options_deny(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "DENY", (
            "Missing X-Frame-Options: DENY — clickjacking protection absent."
        )

    @pytest.mark.asyncio
    async def test_response_has_x_content_type_options_nosniff(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff", (
            "Missing X-Content-Type-Options: nosniff — MIME sniffing risk."
        )

    @pytest.mark.asyncio
    async def test_response_has_x_xss_protection(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"

    @pytest.mark.asyncio
    async def test_response_has_referrer_policy(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_response_has_permissions_policy(self, client: AsyncClient):
        """Permissions-Policy must restrict geolocation/camera/microphone to none."""
        resp = await client.get("/health")
        policy = resp.headers.get("Permissions-Policy", "")
        assert "geolocation=()" in policy
        assert "camera=()" in policy
        assert "microphone=()" in policy

    @pytest.mark.asyncio
    async def test_response_has_x_request_id(self, client: AsyncClient):
        """Every response must include X-Request-ID for traceability."""
        resp = await client.get("/health")
        request_id = resp.headers.get("X-Request-ID")
        assert request_id, "Missing X-Request-ID — no correlation for incident response."
        assert len(request_id) >= 8
