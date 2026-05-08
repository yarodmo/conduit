"""
Conduit Backend — RBAC Permission Matrix
Prompt 3: "RBAC Matrix" — maps role → permissions.

Roles:
  SUPER_ADMIN → all permissions
  ORG_ADMIN   → org management + all project ops
  ORG_MEMBER  → read + own project ops
  ENGINEER    → read + takeoff/BOM execution on assigned projects
  VIEWER      → read only

Granular permissions follow noun:verb pattern.
"""

from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    ORG_MEMBER = "ORG_MEMBER"
    ENGINEER = "ENGINEER"
    VIEWER = "VIEWER"


class Permission(str, Enum):
    # ── Organization ──
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    ORG_DELETE = "org:delete"
    ORG_INVITE = "org:invite"
    ORG_MANAGE_MEMBERS = "org:manage_members"
    ORG_MANAGE_BILLING = "org:manage_billing"

    # ── Projects ──
    PROJECT_CREATE = "project:create"
    PROJECT_READ = "project:read"
    PROJECT_UPDATE = "project:update"
    PROJECT_DELETE = "project:delete"
    PROJECT_MANAGE_MEMBERS = "project:manage_members"

    # ── Takeoffs ──
    TAKEOFF_CREATE = "takeoff:create"
    TAKEOFF_READ = "takeoff:read"
    TAKEOFF_UPDATE = "takeoff:update"
    TAKEOFF_DELETE = "takeoff:delete"
    TAKEOFF_RUN = "takeoff:run"          # Execute AI extraction
    TAKEOFF_APPROVE = "takeoff:approve"  # Approve takeoff for BOM

    # ── BOM ──
    BOM_CREATE = "bom:create"
    BOM_READ = "bom:read"
    BOM_UPDATE = "bom:update"
    BOM_DELETE = "bom:delete"
    BOM_EXPORT = "bom:export"

    # ── Plans (MEP drawings) ──
    PLAN_UPLOAD = "plan:upload"
    PLAN_READ = "plan:read"
    PLAN_DELETE = "plan:delete"

    # ── AI Features ──
    AI_ANALYZE = "ai:analyze"
    AI_CHAT = "ai:chat"

    # ── Reports ──
    REPORT_READ = "report:read"
    REPORT_EXPORT = "report:export"

    # ── Admin ──
    ADMIN_PANEL = "admin:panel"
    ADMIN_IMPERSONATE = "admin:impersonate"


# ══════════════════════════════════════
# PERMISSION MATRIX — Source of truth
# Prompt 3: "Tabla de Permisos por Rol"
# ══════════════════════════════════════

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SUPER_ADMIN: set(Permission),  # All permissions

    Role.ORG_ADMIN: {
        Permission.ORG_READ,
        Permission.ORG_UPDATE,
        Permission.ORG_INVITE,
        Permission.ORG_MANAGE_MEMBERS,
        Permission.ORG_MANAGE_BILLING,
        Permission.PROJECT_CREATE,
        Permission.PROJECT_READ,
        Permission.PROJECT_UPDATE,
        Permission.PROJECT_DELETE,
        Permission.PROJECT_MANAGE_MEMBERS,
        Permission.TAKEOFF_CREATE,
        Permission.TAKEOFF_READ,
        Permission.TAKEOFF_UPDATE,
        Permission.TAKEOFF_DELETE,
        Permission.TAKEOFF_RUN,
        Permission.TAKEOFF_APPROVE,
        Permission.BOM_CREATE,
        Permission.BOM_READ,
        Permission.BOM_UPDATE,
        Permission.BOM_DELETE,
        Permission.BOM_EXPORT,
        Permission.PLAN_UPLOAD,
        Permission.PLAN_READ,
        Permission.PLAN_DELETE,
        Permission.AI_ANALYZE,
        Permission.AI_CHAT,
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
    },

    Role.ORG_MEMBER: {
        Permission.ORG_READ,
        Permission.PROJECT_CREATE,
        Permission.PROJECT_READ,
        Permission.PROJECT_UPDATE,
        Permission.TAKEOFF_CREATE,
        Permission.TAKEOFF_READ,
        Permission.TAKEOFF_UPDATE,
        Permission.TAKEOFF_RUN,
        Permission.BOM_CREATE,
        Permission.BOM_READ,
        Permission.BOM_EXPORT,
        Permission.PLAN_UPLOAD,
        Permission.PLAN_READ,
        Permission.AI_ANALYZE,
        Permission.AI_CHAT,
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
    },

    Role.ENGINEER: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.TAKEOFF_READ,
        Permission.TAKEOFF_RUN,
        Permission.BOM_READ,
        Permission.PLAN_READ,
        Permission.AI_ANALYZE,
        Permission.AI_CHAT,
        Permission.REPORT_READ,
    },

    Role.VIEWER: {
        Permission.ORG_READ,
        Permission.PROJECT_READ,
        Permission.TAKEOFF_READ,
        Permission.BOM_READ,
        Permission.PLAN_READ,
        Permission.REPORT_READ,
    },
}


def has_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def get_permissions(role: Role) -> set[Permission]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, set())
