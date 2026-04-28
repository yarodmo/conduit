"""
Conduit Tests — Unit: RBAC Permission Matrix
Validates every role-permission mapping from permissions.py.

Bliss Systems LLC — APEX Standard
"""

import pytest

from app.core.permissions import Permission, Role, get_permissions, has_permission


class TestRBACMatrix:
    """SUPER_ADMIN has all permissions."""

    def test_super_admin_has_all_permissions(self):
        for perm in Permission:
            assert has_permission(Role.SUPER_ADMIN, perm), (
                f"SUPER_ADMIN missing permission: {perm}"
            )

    """ORG_ADMIN has full org + project management."""

    def test_org_admin_can_manage_org(self):
        assert has_permission(Role.ORG_ADMIN, Permission.ORG_UPDATE)
        assert has_permission(Role.ORG_ADMIN, Permission.ORG_INVITE)
        assert has_permission(Role.ORG_ADMIN, Permission.ORG_MANAGE_MEMBERS)
        assert has_permission(Role.ORG_ADMIN, Permission.ORG_MANAGE_BILLING)

    def test_org_admin_can_run_takeoffs(self):
        assert has_permission(Role.ORG_ADMIN, Permission.TAKEOFF_RUN)
        assert has_permission(Role.ORG_ADMIN, Permission.TAKEOFF_APPROVE)

    def test_org_admin_cannot_access_admin_panel(self):
        """ORG_ADMIN does NOT get platform admin panel."""
        assert not has_permission(Role.ORG_ADMIN, Permission.ADMIN_PANEL)
        assert not has_permission(Role.ORG_ADMIN, Permission.ADMIN_IMPERSONATE)

    """ORG_MEMBER has standard create/run access."""

    def test_org_member_can_create_projects(self):
        assert has_permission(Role.ORG_MEMBER, Permission.PROJECT_CREATE)
        assert has_permission(Role.ORG_MEMBER, Permission.TAKEOFF_CREATE)

    def test_org_member_cannot_manage_members(self):
        assert not has_permission(Role.ORG_MEMBER, Permission.ORG_MANAGE_MEMBERS)
        assert not has_permission(Role.ORG_MEMBER, Permission.PROJECT_MANAGE_MEMBERS)

    def test_org_member_cannot_delete_projects(self):
        assert not has_permission(Role.ORG_MEMBER, Permission.PROJECT_DELETE)

    def test_org_member_cannot_approve_takeoffs(self):
        """Only admin can approve — keeps audit trail clean."""
        assert not has_permission(Role.ORG_MEMBER, Permission.TAKEOFF_APPROVE)

    """ENGINEER has execution access, no management."""

    def test_engineer_can_run_takeoffs(self):
        assert has_permission(Role.ENGINEER, Permission.TAKEOFF_RUN)
        assert has_permission(Role.ENGINEER, Permission.AI_ANALYZE)

    def test_engineer_cannot_create_projects(self):
        assert not has_permission(Role.ENGINEER, Permission.PROJECT_CREATE)
        assert not has_permission(Role.ENGINEER, Permission.TAKEOFF_CREATE)

    def test_engineer_cannot_export_bom(self):
        """Engineer reads but cannot export — license control."""
        assert not has_permission(Role.ENGINEER, Permission.BOM_EXPORT)

    def test_engineer_cannot_delete_anything(self):
        assert not has_permission(Role.ENGINEER, Permission.TAKEOFF_DELETE)
        assert not has_permission(Role.ENGINEER, Permission.PLAN_DELETE)

    """VIEWER is strictly read-only."""

    def test_viewer_can_read_all_core_resources(self):
        assert has_permission(Role.VIEWER, Permission.PROJECT_READ)
        assert has_permission(Role.VIEWER, Permission.TAKEOFF_READ)
        assert has_permission(Role.VIEWER, Permission.BOM_READ)
        assert has_permission(Role.VIEWER, Permission.PLAN_READ)

    def test_viewer_cannot_write_anything(self):
        write_permissions = [
            Permission.PROJECT_CREATE,
            Permission.TAKEOFF_CREATE,
            Permission.TAKEOFF_RUN,
            Permission.BOM_CREATE,
            Permission.PLAN_UPLOAD,
            Permission.AI_ANALYZE,
        ]
        for perm in write_permissions:
            assert not has_permission(Role.VIEWER, perm), (
                f"VIEWER should not have: {perm}"
            )

    """Role escalation must not be possible."""

    def test_unknown_role_returns_empty_permissions(self):
        """Any role not in the matrix yields zero permissions."""
        class FakeRole(str):
            pass

        fake = FakeRole("HACKER")
        perms = get_permissions(fake)  # type: ignore
        assert len(perms) == 0

    """Permission hierarchy is non-overlapping where required."""

    def test_engineer_subset_of_org_member(self):
        """ENGINEER permissions ⊆ ORG_MEMBER permissions."""
        engineer_perms = get_permissions(Role.ENGINEER)
        member_perms = get_permissions(Role.ORG_MEMBER)
        extras = engineer_perms - member_perms
        assert not extras, f"ENGINEER has perms not in ORG_MEMBER: {extras}"

    def test_viewer_subset_of_engineer(self):
        """VIEWER permissions ⊆ ENGINEER permissions."""
        viewer_perms = get_permissions(Role.VIEWER)
        engineer_perms = get_permissions(Role.ENGINEER)
        extras = viewer_perms - engineer_perms
        assert not extras, f"VIEWER has perms not in ENGINEER: {extras}"
