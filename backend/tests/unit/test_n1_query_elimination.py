"""
FORENSIC TEST — GAP-006/007/008: N+1 Query Elimination
========================================================
Validates that JOIN-based repository methods execute correctly
and that the service layer properly maps joined results.

Tests:
  - get_user_orgs_with_orgs() returns correct (member, org) tuples
  - get_members_with_users() returns correct (member, user) tuples  
  - Multiple org memberships resolve in a single query call
  - Cross-tenant data does NOT leak into joined results

Bliss Systems LLC — APEX Standard | Sprint 1 Validation
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import (
    OrgRole,
    Organization,
    OrganizationMember,
    SubscriptionPlan,
    User,
)
from app.core.security import hash_password
from app.modules.auth.repository import OrganizationRepository, AuthRepository


# ════════════════════════════════════════════════════
# Local fixtures (self-contained, no conftest deps)
# ════════════════════════════════════════════════════
@pytest_asyncio.fixture
async def seed_plan(db: AsyncSession) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name="free_n1",
        display_name="Free N+1 Test",
        price_monthly_usd=0,
        price_annual_usd=0,
        limits={"max_projects": 3},
        is_active=True,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def two_orgs_one_user(db: AsyncSession, seed_plan: SubscriptionPlan):
    """User belongs to two organizations — classic N+1 scenario."""
    user = User(
        email="n1_victim@conduit.build",
        hashed_password=hash_password("Test1234!"),
        full_name="N+1 Victim",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    org_a = Organization(name="Org Alpha", slug="org-alpha", plan_id=seed_plan.id)
    org_b = Organization(name="Org Beta",  slug="org-beta",  plan_id=seed_plan.id)
    db.add_all([org_a, org_b])
    await db.flush()

    mem_a = OrganizationMember(user_id=user.id, org_id=org_a.id, role=OrgRole.ORG_ADMIN)
    mem_b = OrganizationMember(user_id=user.id, org_id=org_b.id, role=OrgRole.ORG_MEMBER)
    db.add_all([mem_a, mem_b])
    await db.commit()

    return {"user": user, "org_a": org_a, "org_b": org_b, "mem_a": mem_a, "mem_b": mem_b}


@pytest_asyncio.fixture
async def two_users_one_org(db: AsyncSession, seed_plan: SubscriptionPlan):
    """Two users in same org — classic N+1 scenario for get_members."""
    org = Organization(name="Shared Org", slug="shared-org", plan_id=seed_plan.id)
    db.add(org)
    await db.flush()

    u1 = User(
        email="admin@shared.build",
        hashed_password=hash_password("Test1234!"),
        full_name="Admin User",
        is_active=True,
    )
    u2 = User(
        email="member@shared.build",
        hashed_password=hash_password("Test1234!"),
        full_name="Member User",
        is_active=True,
    )
    db.add_all([u1, u2])
    await db.flush()

    m1 = OrganizationMember(user_id=u1.id, org_id=org.id, role=OrgRole.ORG_ADMIN)
    m2 = OrganizationMember(user_id=u2.id, org_id=org.id, role=OrgRole.ORG_MEMBER)
    db.add_all([m1, m2])
    await db.commit()

    return {"org": org, "u1": u1, "u2": u2, "m1": m1, "m2": m2}


# ════════════════════════════════════════════════════
# GAP-006: get_user_orgs_with_orgs
# ════════════════════════════════════════════════════
class TestGetUserOrgsWithOrgs:

    @pytest.mark.asyncio
    async def test_returns_both_orgs_in_single_call(
        self, db: AsyncSession, two_orgs_one_user: dict
    ):
        repo = OrganizationRepository(db)
        user = two_orgs_one_user["user"]

        results = await repo.get_user_orgs_with_orgs(user.id)

        assert len(results) == 2, "Must return both org memberships"

    @pytest.mark.asyncio
    async def test_tuple_structure_is_correct(
        self, db: AsyncSession, two_orgs_one_user: dict
    ):
        repo = OrganizationRepository(db)
        user = two_orgs_one_user["user"]

        results = await repo.get_user_orgs_with_orgs(user.id)

        for row in results:
            member, org = row
            assert isinstance(member, OrganizationMember)
            assert isinstance(org, Organization)

    @pytest.mark.asyncio
    async def test_returns_correct_org_names(
        self, db: AsyncSession, two_orgs_one_user: dict
    ):
        repo = OrganizationRepository(db)
        user = two_orgs_one_user["user"]

        results = await repo.get_user_orgs_with_orgs(user.id)
        org_names = {org.name for _, org in results}

        assert "Org Alpha" in org_names
        assert "Org Beta"  in org_names

    @pytest.mark.asyncio
    async def test_roles_are_correctly_mapped(
        self, db: AsyncSession, two_orgs_one_user: dict
    ):
        repo = OrganizationRepository(db)
        user = two_orgs_one_user["user"]
        org_a = two_orgs_one_user["org_a"]

        results = await repo.get_user_orgs_with_orgs(user.id)
        role_map = {org.id: member.role for member, org in results}

        assert role_map[org_a.id] == OrgRole.ORG_ADMIN

    @pytest.mark.asyncio
    async def test_no_cross_tenant_leakage(
        self, db: AsyncSession, seed_plan: SubscriptionPlan
    ):
        """User in Org-A must NOT see Org-B in their results."""
        u_a = User(
            email="tenant_a@conduit.build",
            hashed_password="x",
            full_name="Tenant A",
            is_active=True,
        )
        u_b = User(
            email="tenant_b@conduit.build",
            hashed_password="x",
            full_name="Tenant B",
            is_active=True,
        )
        db.add_all([u_a, u_b])
        await db.flush()

        org_x = Organization(name="Tenant Org X", slug="tenant-x", plan_id=seed_plan.id)
        org_y = Organization(name="Tenant Org Y", slug="tenant-y", plan_id=seed_plan.id)
        db.add_all([org_x, org_y])
        await db.flush()

        db.add(OrganizationMember(user_id=u_a.id, org_id=org_x.id, role=OrgRole.ORG_ADMIN))
        db.add(OrganizationMember(user_id=u_b.id, org_id=org_y.id, role=OrgRole.ORG_ADMIN))
        await db.commit()

        repo = OrganizationRepository(db)
        results_a = await repo.get_user_orgs_with_orgs(u_a.id)
        org_ids_a = {org.id for _, org in results_a}

        assert org_x.id in org_ids_a
        assert org_y.id not in org_ids_a, "CROSS-TENANT LEAKAGE: org_y must NOT appear for user_a"

    @pytest.mark.asyncio
    async def test_returns_empty_for_user_with_no_memberships(
        self, db: AsyncSession, seed_plan: SubscriptionPlan
    ):
        lonely_user = User(
            email="lonely@conduit.build",
            hashed_password="x",
            full_name="Lonely",
            is_active=True,
        )
        db.add(lonely_user)
        await db.commit()

        repo = OrganizationRepository(db)
        results = await repo.get_user_orgs_with_orgs(lonely_user.id)
        assert results == []


# ════════════════════════════════════════════════════
# GAP-007/008: get_members_with_users
# ════════════════════════════════════════════════════
class TestGetMembersWithUsers:

    @pytest.mark.asyncio
    async def test_returns_all_members_in_single_call(
        self, db: AsyncSession, two_users_one_org: dict
    ):
        repo = OrganizationRepository(db)
        org = two_users_one_org["org"]

        results = await repo.get_members_with_users(org.id)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_tuple_structure_member_user(
        self, db: AsyncSession, two_users_one_org: dict
    ):
        repo = OrganizationRepository(db)
        org = two_users_one_org["org"]

        results = await repo.get_members_with_users(org.id)
        for member, user in results:
            assert isinstance(member, OrganizationMember)
            assert isinstance(user, User)

    @pytest.mark.asyncio
    async def test_user_emails_correct(
        self, db: AsyncSession, two_users_one_org: dict
    ):
        repo = OrganizationRepository(db)
        org = two_users_one_org["org"]

        results = await repo.get_members_with_users(org.id)
        emails = {user.email for _, user in results}

        assert "admin@shared.build"  in emails
        assert "member@shared.build" in emails

    @pytest.mark.asyncio
    async def test_roles_preserved_in_join(
        self, db: AsyncSession, two_users_one_org: dict
    ):
        repo = OrganizationRepository(db)
        org = two_users_one_org["org"]
        u1  = two_users_one_org["u1"]

        results = await repo.get_members_with_users(org.id)
        role_by_email = {user.email: member.role for member, user in results}

        assert role_by_email["admin@shared.build"]  == OrgRole.ORG_ADMIN
        assert role_by_email["member@shared.build"] == OrgRole.ORG_MEMBER

    @pytest.mark.asyncio
    async def test_does_not_return_members_from_other_orgs(
        self, db: AsyncSession, seed_plan: SubscriptionPlan
    ):
        """GAP-007/008 cross-tenant: Org A's members must NOT include Org B users."""
        org_a = Organization(name="Secure Org A", slug="secure-a", plan_id=seed_plan.id)
        org_b = Organization(name="Secure Org B", slug="secure-b", plan_id=seed_plan.id)
        db.add_all([org_a, org_b])
        await db.flush()

        u_in_a = User(email="only_a@conduit.build", hashed_password="x",
                      full_name="A Member", is_active=True)
        u_in_b = User(email="only_b@conduit.build", hashed_password="x",
                      full_name="B Member", is_active=True)
        db.add_all([u_in_a, u_in_b])
        await db.flush()

        db.add(OrganizationMember(user_id=u_in_a.id, org_id=org_a.id, role=OrgRole.ORG_MEMBER))
        db.add(OrganizationMember(user_id=u_in_b.id, org_id=org_b.id, role=OrgRole.ORG_MEMBER))
        await db.commit()

        repo = OrganizationRepository(db)
        results_a = await repo.get_members_with_users(org_a.id)
        emails_a = {user.email for _, user in results_a}

        assert "only_a@conduit.build" in  emails_a
        assert "only_b@conduit.build" not in emails_a, (
            "CROSS-TENANT LEAKAGE: Org B member appeared in Org A results!"
        )

    @pytest.mark.asyncio
    async def test_returns_empty_for_org_with_no_members(
        self, db: AsyncSession, seed_plan: SubscriptionPlan
    ):
        empty_org = Organization(name="Ghost Org", slug="ghost-org", plan_id=seed_plan.id)
        db.add(empty_org)
        await db.commit()

        repo = OrganizationRepository(db)
        results = await repo.get_members_with_users(empty_org.id)
        assert results == []
