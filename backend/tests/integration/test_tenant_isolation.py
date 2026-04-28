"""
Conduit Tests — Integration: Tenant Isolation (X-Organization-ID)
Prompt 3: "Middleware X-Organization-ID → tenant isolation en todo request"

Tests:
- Missing X-Organization-ID → 400
- Invalid UUID → 400
- Non-existent org → 404
- User not in org → 403 (CROSS-TENANT ATTACK)
- Valid member gets access
- Org data only returns own members

CRITICAL: These tests validate the #1 security law of Conduit.
A breach here would expose ALL customer data across tenants.

Bliss Systems LLC — APEX Standard
"""

import uuid

import pytest
from httpx import AsyncClient

from app.core.security import hash_password
from app.models.auth import OrgRole, Organization, OrganizationMember, SubscriptionPlan, User


class TestTenantIsolation:
    async def test_missing_org_header_returns_400(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """
        /organizations/me requires X-Organization-ID.
        Missing header → 400 ORG_ID_MISSING.
        """
        resp = await client.get(
            "/api/v1/organizations/me",
            headers={"Authorization": auth_headers["Authorization"]},
            # No X-Organization-ID header
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "ORG_ID_MISSING"

    async def test_invalid_org_id_format_returns_400(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Non-UUID X-Organization-ID → 400 INVALID_ORG_ID."""
        resp = await client.get(
            "/api/v1/organizations/me",
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": "not-a-uuid",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_ORG_ID"

    async def test_nonexistent_org_returns_404(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Valid UUID but non-existent org → 404 ORG_NOT_FOUND."""
        resp = await client.get(
            "/api/v1/organizations/me",
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "ORG_NOT_FOUND"

    async def test_cross_tenant_access_blocked(
        self, client: AsyncClient, free_plan, db
    ):
        """
        CRITICAL: User A cannot access Org B's data.
        This is the most important security test in the suite.
        """
        # Create User A + Org A
        user_a = User(
            email="user_a@conduit.build",
            hashed_password=hash_password("PassA123!"),
            full_name="User A",
            is_active=True,
        )
        db.add(user_a)
        await db.flush()

        org_a = Organization(
            name="Org A",
            slug="org-a-isolation-test",
            plan_id=free_plan.id,
        )
        db.add(org_a)
        await db.flush()

        db.add(OrganizationMember(
            user_id=user_a.id,
            org_id=org_a.id,
            role=OrgRole.ORG_ADMIN,
        ))

        # Create Org B (User A is NOT a member)
        org_b = Organization(
            name="Org B",
            slug="org-b-isolation-test",
            plan_id=free_plan.id,
        )
        db.add(org_b)
        await db.commit()

        # Login as User A
        login_resp = await client.post("/api/v1/login", json={
            "email": "user_a@conduit.build",
            "password": "PassA123!",
        })
        assert login_resp.status_code == 200
        token_a = login_resp.json()["access_token"]

        # Attempt to access Org B's data using User A's token — MUST FAIL
        resp = await client.get(
            "/api/v1/organizations/me",
            headers={
                "Authorization": f"Bearer {token_a}",
                "X-Organization-ID": str(org_b.id),  # Org B UUID
            },
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "NOT_ORG_MEMBER"

    async def test_member_can_access_own_org(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Valid member with correct org header gets org detail."""
        resp = await client.get(
            "/api/v1/organizations/me",
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": auth_headers["X-Organization-ID"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == auth_headers["X-Organization-ID"]

    async def test_org_members_list_only_returns_own_members(
        self, client: AsyncClient, auth_headers, free_plan, test_user, db
    ):
        """
        Members endpoint only returns members of the org in the header.
        Must not leak other org's member list.
        """
        # Create another org with different user
        user_b = User(
            email="user_b@conduit.build",
            hashed_password=hash_password("PassB123!"),
            full_name="User B",
            is_active=True,
        )
        db.add(user_b)
        await db.flush()

        org_b = Organization(name="Org B", slug="org-b-members", plan_id=free_plan.id)
        db.add(org_b)
        await db.flush()

        db.add(OrganizationMember(
            user_id=user_b.id,
            org_id=org_b.id,
            role=OrgRole.ORG_ADMIN,
        ))
        await db.commit()

        # Get members of test_user's org
        resp = await client.get(
            "/api/v1/organizations/members",
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": auth_headers["X-Organization-ID"],
            },
        )
        assert resp.status_code == 200
        members = resp.json()

        # Only test_user should appear, NOT user_b
        emails = [m["email"] for m in members]
        assert "user_b@conduit.build" not in emails
        assert test_user["email"] in emails
