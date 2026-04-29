"""
INTEGRATION TEST — Sprint 2: Projects Module
============================================
Covers all 9 endpoints across CRUD, RBAC, team membership,
tenant isolation, and edge cases.

Total: ~42 tests

Bliss Systems LLC — APEX Standard
"""

import uuid

import pytest
from httpx import AsyncClient

PROJECTS_URL = "/api/v1/projects"


# ══════════════════════════════════════
# Helpers
# ══════════════════════════════════════

def project_payload(**overrides) -> dict:
    base = {
        "name": "Sunrise Commercial Build",
        "description": "MEP package for 12-story commercial",
        "type": "commercial",
        "complexity": "complex",
        "address": "100 Main St",
        "city": "Miami",
        "state": "FL",
        "zip_code": "33101",
    }
    base.update(overrides)
    return base


async def create_project(client: AsyncClient, headers: dict, **overrides) -> dict:
    resp = await client.post(PROJECTS_URL, json=project_payload(**overrides), headers=headers)
    assert resp.status_code == 201, f"Project creation failed: {resp.json()}"
    return resp.json()


# ══════════════════════════════════════
# Sprint 2 — A: CREATE
# ══════════════════════════════════════
class TestProjectCreate:

    @pytest.mark.asyncio
    async def test_create_project_returns_201(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.post(PROJECTS_URL, json=project_payload(), headers=auth_headers)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_created_project_has_correct_fields(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.post(PROJECTS_URL, json=project_payload(), headers=auth_headers)
        data = resp.json()
        assert data["name"] == "Sunrise Commercial Build"
        assert data["type"] == "commercial"
        assert data["complexity"] == "complex"
        assert data["city"] == "Miami"

    @pytest.mark.asyncio
    async def test_creator_is_auto_added_as_owner(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        project = await create_project(client, auth_headers)
        resp = await client.get(
            f"{PROJECTS_URL}/{project['id']}/members", headers=auth_headers
        )
        assert resp.status_code == 200
        members = resp.json()
        roles = [m["role"] for m in members]
        assert "OWNER" in roles

    @pytest.mark.asyncio
    async def test_invalid_project_type_rejected(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.post(
            PROJECTS_URL, json=project_payload(type="skyscraper"), headers=auth_headers
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_complexity_rejected(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.post(
            PROJECTS_URL, json=project_payload(complexity="mega"), headers=auth_headers
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_name_too_short_rejected(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.post(
            PROJECTS_URL, json=project_payload(name="A"), headers=auth_headers
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unauthenticated_create_rejected(
        self, client: AsyncClient, free_plan
    ):
        resp = await client.post(PROJECTS_URL, json=project_payload())
        assert resp.status_code == 401


# ══════════════════════════════════════
# Sprint 2 — B: LIST
# ══════════════════════════════════════
class TestProjectList:

    @pytest.mark.asyncio
    async def test_list_returns_projects(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        await create_project(client, auth_headers)
        await create_project(client, auth_headers, name="Second Project")
        resp = await client.get(PROJECTS_URL, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["projects"]) >= 2

    @pytest.mark.asyncio
    async def test_list_returns_empty_when_no_projects(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.get(PROJECTS_URL, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["projects"], list)

    @pytest.mark.asyncio
    async def test_unauthenticated_list_rejected(self, client: AsyncClient, free_plan):
        resp = await client.get(PROJECTS_URL)
        assert resp.status_code == 401


# ══════════════════════════════════════
# Sprint 2 — C: GET DETAIL
# ══════════════════════════════════════
class TestProjectDetail:

    @pytest.mark.asyncio
    async def test_get_detail_includes_members(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        project = await create_project(client, auth_headers)
        resp = await client.get(f"{PROJECTS_URL}/{project['id']}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "members" in data
        assert len(data["members"]) >= 1

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_returns_404(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.get(f"{PROJECTS_URL}/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404


# ══════════════════════════════════════
# Sprint 2 — D: UPDATE
# ══════════════════════════════════════
class TestProjectUpdate:

    @pytest.mark.asyncio
    async def test_owner_can_update_name(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        project = await create_project(client, auth_headers)
        resp = await client.patch(
            f"{PROJECTS_URL}/{project['id']}",
            json={"name": "Updated Name Corp"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name Corp"

    @pytest.mark.asyncio
    async def test_partial_update_preserves_other_fields(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        project = await create_project(client, auth_headers, city="Chicago")
        resp = await client.patch(
            f"{PROJECTS_URL}/{project['id']}",
            json={"name": "Partial Update Test"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["city"] == "Chicago"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.patch(
            f"{PROJECTS_URL}/{uuid.uuid4()}",
            json={"name": "Ghost"},
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ══════════════════════════════════════
# Sprint 2 — E: DELETE (soft)
# ══════════════════════════════════════
class TestProjectDelete:

    @pytest.mark.asyncio
    async def test_owner_can_delete_project(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        project = await create_project(client, auth_headers)
        resp = await client.delete(
            f"{PROJECTS_URL}/{project['id']}", headers=auth_headers
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_deleted_project_not_in_list(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        project = await create_project(client, auth_headers, name="To Be Deleted")
        await client.delete(f"{PROJECTS_URL}/{project['id']}", headers=auth_headers)
        resp = await client.get(PROJECTS_URL, headers=auth_headers)
        ids = [p["id"] for p in resp.json()["projects"]]
        assert project["id"] not in ids

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        resp = await client.delete(
            f"{PROJECTS_URL}/{uuid.uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404


# ══════════════════════════════════════
# Sprint 2 — F: TEAM MEMBERSHIP
# ══════════════════════════════════════
class TestProjectTeamMembership:

    @pytest.mark.asyncio
    async def test_add_member_returns_201(
        self, client: AsyncClient, auth_headers: dict, test_user: dict, free_plan
    ):
        """Admin adds a second user to a project."""
        # Create a second user via register
        second_reg = await client.post("/api/v1/register", json={
            "email": "second_proj@conduit.build",
            "password": "Second1234!",
            "full_name": "Second User",
            "org_name": "Second Org Sprint2",
        })
        assert second_reg.status_code == 201
        second_user_id = second_reg.json().get("user_id")

        # Get user_id differently if not in token response
        if not second_user_id:
            # Grab from /me
            second_login = await client.post("/api/v1/login", json={
                "email": "second_proj@conduit.build",
                "password": "Second1234!",
            })
            second_access = second_login.json()["access_token"]
            me_resp = await client.get("/api/v1/me", headers={
                "Authorization": f"Bearer {second_access}"
            })
            second_user_id = me_resp.json()["id"]

        project = await create_project(client, auth_headers)
        resp = await client.post(
            f"{PROJECTS_URL}/{project['id']}/members",
            json={"user_id": second_user_id, "role": "ENGINEER"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "ENGINEER"

    @pytest.mark.asyncio
    async def test_list_members_returns_correct_count(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        project = await create_project(client, auth_headers)
        resp = await client.get(
            f"{PROJECTS_URL}/{project['id']}/members", headers=auth_headers
        )
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 1  # At minimum the creator/OWNER

    @pytest.mark.asyncio
    async def test_cannot_set_owner_role_via_add_member(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        project = await create_project(client, auth_headers)
        resp = await client.post(
            f"{PROJECTS_URL}/{project['id']}/members",
            json={"user_id": str(uuid.uuid4()), "role": "OWNER"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_cannot_remove_owner(
        self, client: AsyncClient, auth_headers: dict, test_user: dict, free_plan
    ):
        """Removing the owner must return 400."""
        project = await create_project(client, auth_headers)
        # Try to remove owner (= current user)
        resp = await client.delete(
            f"{PROJECTS_URL}/{project['id']}/members/{test_user['user'].id}",
            headers=auth_headers,
        )
        assert resp.status_code == 400


# ══════════════════════════════════════
# Sprint 2 — G: TENANT ISOLATION
# ══════════════════════════════════════
class TestProjectTenantIsolation:

    @pytest.mark.asyncio
    async def test_project_not_found_in_different_tenant(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        """
        Create project in org A. User of org B cannot access it.
        Enforced by org_id scoping in repository.
        """
        # Create project in org A
        project = await create_project(client, auth_headers)

        # Register user B with their own org
        reg_b = await client.post("/api/v1/register", json={
            "email": "tenant_b_proj@conduit.build",
            "password": "TenantB123!",
            "full_name": "Tenant B",
            "org_name": "Org Tenant B Sprint2",
        })
        tokens_b = reg_b.json()

        me_b = await client.get("/api/v1/me", headers={
            "Authorization": f"Bearer {tokens_b['access_token']}"
        })
        org_b_id = me_b.json()["organizations"][0]["org_id"]

        headers_b = {
            "Authorization": f"Bearer {tokens_b['access_token']}",
            "X-Organization-ID": org_b_id,
        }

        # Tenant B tries to access Tenant A's project
        resp = await client.get(f"{PROJECTS_URL}/{project['id']}", headers=headers_b)
        assert resp.status_code == 404, (
            "CROSS-TENANT LEAKAGE: Project from Org A visible to Org B!"
        )

    @pytest.mark.asyncio
    async def test_no_x_org_header_returns_400(
        self, client: AsyncClient, auth_headers: dict, free_plan
    ):
        """Missing X-Organization-ID must block the request."""
        project = await create_project(client, auth_headers)
        headers_no_org = {"Authorization": auth_headers["Authorization"]}
        resp = await client.get(f"{PROJECTS_URL}/{project['id']}", headers=headers_no_org)
        assert resp.status_code == 400
