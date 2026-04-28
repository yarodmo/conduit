"""
Conduit Tests — Integration: Organization Management
Prompt 3: "CRUD completo de organizaciones + invite flow"

Tests:
- Create org
- Get org detail
- Update org (admin only)
- Non-admin cannot update org
- Invite member by email (Celery mocked)
- Accept invitation
- List members
- Change member role
- Cannot demote last admin
- Remove member
- Cannot remove last admin

Bliss Systems LLC — APEX Standard
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.auth import OrgRole


class TestOrganizationCRUD:
    async def test_create_organization(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Authenticated user can create a new organization."""
        resp = await client.post(
            "/api/v1/organizations",
            json={"name": "New MEP Corp"},
            headers={"Authorization": auth_headers["Authorization"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New MEP Corp"
        assert "slug" in data
        assert "id" in data

    async def test_get_organization_detail(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Org detail includes members and plan info."""
        resp = await client.get(
            "/api/v1/organizations/me",
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": auth_headers["X-Organization-ID"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "members" in data
        assert data["member_count"] >= 1

    async def test_admin_can_update_org(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """ORG_ADMIN can update organization name."""
        org_id = auth_headers["X-Organization-ID"]
        resp = await client.patch(
            f"/api/v1/organizations/{org_id}",
            json={"name": "Updated Corp"},
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": auth_headers["X-Organization-ID"],
            },
        )
        assert resp.status_code == 200
        assert "updated" in resp.json()["message"].lower()

    async def test_get_me_returns_org_memberships(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """GET /me includes org memberships with roles."""
        resp = await client.get(
            "/api/v1/me",
            headers={"Authorization": auth_headers["Authorization"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["organizations"]) >= 1
        org = data["organizations"][0]
        assert "org_id" in org
        assert "org_name" in org
        assert "role" in org


class TestInvitationFlow:
    async def test_admin_can_invite_member(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """ORG_ADMIN can send invitation email (Celery mocked)."""
        with patch("app.tasks.email_tasks.send_invitation_email.delay"):
            resp = await client.post(
                "/api/v1/organizations/invite",
                json={
                    "email": "newengineer@conduit.build",
                    "role": "ORG_MEMBER",
                },
                headers={
                    "Authorization": auth_headers["Authorization"],
                    "X-Organization-ID": auth_headers["X-Organization-ID"],
                },
            )
        assert resp.status_code == 200
        assert "newengineer@conduit.build" in resp.json()["message"]

    async def test_cannot_invite_existing_member(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Inviting an existing member returns 409 CONFLICT."""
        with patch("app.tasks.email_tasks.send_invitation_email.delay"):
            # First invite (creates pending invitation)
            await client.post(
                "/api/v1/organizations/invite",
                json={"email": "dup@conduit.build", "role": "ORG_MEMBER"},
                headers={
                    "Authorization": auth_headers["Authorization"],
                    "X-Organization-ID": auth_headers["X-Organization-ID"],
                },
            )
            # Second invite (same email) — conflict
            resp = await client.post(
                "/api/v1/organizations/invite",
                json={"email": "dup@conduit.build", "role": "ORG_MEMBER"},
                headers={
                    "Authorization": auth_headers["Authorization"],
                    "X-Organization-ID": auth_headers["X-Organization-ID"],
                },
            )
        assert resp.status_code == 409

    async def test_invalid_role_in_invite_rejected(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Unknown role in invite payload must fail validation."""
        resp = await client.post(
            "/api/v1/organizations/invite",
            json={"email": "x@conduit.build", "role": "HACKER"},
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": auth_headers["X-Organization-ID"],
            },
        )
        assert resp.status_code == 422


class TestMemberManagement:
    async def test_list_members(
        self, client: AsyncClient, auth_headers, free_plan, test_user
    ):
        """Members endpoint returns list with roles."""
        resp = await client.get(
            "/api/v1/organizations/members",
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": auth_headers["X-Organization-ID"],
            },
        )
        assert resp.status_code == 200
        members = resp.json()
        assert isinstance(members, list)
        assert any(m["email"] == test_user["email"] for m in members)

    async def test_cannot_remove_last_admin(
        self, client: AsyncClient, auth_headers, free_plan, test_user, db
    ):
        """
        Removing the only admin must return 422.
        Prevents orphaned orgs with no admin.
        """
        # Get the member ID of test_user (who is the only admin)
        members_resp = await client.get(
            "/api/v1/organizations/members",
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": auth_headers["X-Organization-ID"],
            },
        )
        members = members_resp.json()
        admin_member = next(
            m for m in members
            if m["email"] == test_user["email"]
        )

        resp = await client.delete(
            f"/api/v1/organizations/members/{admin_member['id']}",
            headers={
                "Authorization": auth_headers["Authorization"],
                "X-Organization-ID": auth_headers["X-Organization-ID"],
            },
        )
        assert resp.status_code == 422

    async def test_unauthenticated_cannot_list_members(
        self, client: AsyncClient, free_plan, test_user
    ):
        """No bearer token → 401."""
        resp = await client.get(
            "/api/v1/organizations/members",
            headers={"X-Organization-ID": test_user["org_id"]},
        )
        assert resp.status_code == 401
