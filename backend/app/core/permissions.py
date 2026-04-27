"""
Conduit Backend — RBAC Permissions Matrix
Prompt 0.1 — BOLA Mitigation (Capa 2)

Single source of truth for role-based access control.
Every endpoint must check against this matrix.
"""

from enum import Enum


class Role(str, Enum):
    """Organization-level roles."""
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    ENGINEER = "ENGINEER"
    ESTIMATOR = "ESTIMATOR"
    FIELD_TECH = "FIELD_TECH"
    VIEWER = "VIEWER"
    PE_REVIEWER = "PE_REVIEWER"  # ADR-004: M15 Design Simulation


class Permission(str, Enum):
    """Granular permissions mapped to roles."""

    # ── Auth & Org ──
    ORG_MANAGE = "org:manage"
    ORG_INVITE = "org:invite"
    ORG_BILLING = "org:billing"

    # ── Projects ──
    PROJECT_CREATE = "project:create"
    PROJECT_EDIT = "project:edit"
    PROJECT_DELETE = "project:delete"
    PROJECT_VIEW = "project:view"

    # ── Plans (M3) ──
    PLAN_UPLOAD = "plan:upload"
    PLAN_VIEW = "plan:view"
    PLAN_DELETE = "plan:delete"

    # ── Takeoff (M5 — THE WEDGE) ──
    TAKEOFF_RUN = "takeoff:run"
    TAKEOFF_APPROVE = "takeoff:approve"
    TAKEOFF_EXPORT = "takeoff:export"
    TAKEOFF_VIEW = "takeoff:view"

    # ── Field (M6) ──
    FIELD_UPDATE_PROGRESS = "field:update_progress"
    FIELD_SUBMIT_PHOTO = "field:submit_photo"
    FIELD_VIEW_ZONES = "field:view_zones"
    FIELD_ASSIGN_ZONES = "field:assign_zones"

    # ── RFI (M7) ──
    RFI_CREATE = "rfi:create"
    RFI_RESPOND = "rfi:respond"
    RFI_APPROVE = "rfi:approve"
    RFI_VIEW = "rfi:view"

    # ── Reports (M9) ──
    REPORT_GENERATE = "report:generate"
    REPORT_VIEW = "report:view"

    # ── AI Assistant (M10) ──
    ASSISTANT_QUERY = "assistant:query"

    # ── Design Simulation (M15 — ADR-004) ──
    SIMULATION_CREATE = "simulation:create"
    SIMULATION_VIEW = "simulation:view"
    SIMULATION_EXPORT = "simulation:export"

    # ── PE Review (M15) ──
    PE_REVIEW_QUEUE = "pe:review_queue"
    PE_REVIEW_SIMULATION = "pe:review_simulation"
    PE_APPROVE_SIMULATION = "pe:approve_simulation"
    PE_REJECT_SIMULATION = "pe:reject_simulation"
    PE_CORRECT_SIMULATION = "pe:correct_simulation"
    PE_VIEW_METRICS = "pe:view_metrics"


# ══════════════════════════════════════
# PERMISSION MATRIX — IMMUTABLE
# ══════════════════════════════════════
# Roles → Set of permissions
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.OWNER: set(Permission),  # All permissions

    Role.ADMIN: {
        Permission.ORG_MANAGE, Permission.ORG_INVITE,
        Permission.PROJECT_CREATE, Permission.PROJECT_EDIT,
        Permission.PROJECT_DELETE, Permission.PROJECT_VIEW,
        Permission.PLAN_UPLOAD, Permission.PLAN_VIEW, Permission.PLAN_DELETE,
        Permission.TAKEOFF_RUN, Permission.TAKEOFF_APPROVE,
        Permission.TAKEOFF_EXPORT, Permission.TAKEOFF_VIEW,
        Permission.FIELD_VIEW_ZONES, Permission.FIELD_ASSIGN_ZONES,
        Permission.RFI_CREATE, Permission.RFI_RESPOND,
        Permission.RFI_APPROVE, Permission.RFI_VIEW,
        Permission.REPORT_GENERATE, Permission.REPORT_VIEW,
        Permission.ASSISTANT_QUERY,
        Permission.SIMULATION_CREATE, Permission.SIMULATION_VIEW,
        Permission.SIMULATION_EXPORT,
    },

    Role.PROJECT_MANAGER: {
        Permission.PROJECT_CREATE, Permission.PROJECT_EDIT, Permission.PROJECT_VIEW,
        Permission.PLAN_UPLOAD, Permission.PLAN_VIEW,
        Permission.TAKEOFF_RUN, Permission.TAKEOFF_APPROVE,
        Permission.TAKEOFF_EXPORT, Permission.TAKEOFF_VIEW,
        Permission.FIELD_VIEW_ZONES, Permission.FIELD_ASSIGN_ZONES,
        Permission.RFI_CREATE, Permission.RFI_RESPOND,
        Permission.RFI_APPROVE, Permission.RFI_VIEW,
        Permission.REPORT_GENERATE, Permission.REPORT_VIEW,
        Permission.ASSISTANT_QUERY,
        Permission.SIMULATION_CREATE, Permission.SIMULATION_VIEW,
        Permission.SIMULATION_EXPORT,
    },

    Role.ENGINEER: {
        Permission.PROJECT_VIEW,
        Permission.PLAN_UPLOAD, Permission.PLAN_VIEW,
        Permission.TAKEOFF_RUN, Permission.TAKEOFF_VIEW,
        Permission.TAKEOFF_EXPORT,
        Permission.FIELD_VIEW_ZONES,
        Permission.RFI_CREATE, Permission.RFI_RESPOND, Permission.RFI_VIEW,
        Permission.REPORT_VIEW,
        Permission.ASSISTANT_QUERY,
        Permission.SIMULATION_CREATE, Permission.SIMULATION_VIEW,
    },

    Role.ESTIMATOR: {
        Permission.PROJECT_VIEW,
        Permission.PLAN_VIEW,
        Permission.TAKEOFF_RUN, Permission.TAKEOFF_VIEW,
        Permission.TAKEOFF_EXPORT, Permission.TAKEOFF_APPROVE,
        Permission.REPORT_GENERATE, Permission.REPORT_VIEW,
        Permission.ASSISTANT_QUERY,
    },

    Role.FIELD_TECH: {
        Permission.PROJECT_VIEW,
        Permission.PLAN_VIEW,
        Permission.TAKEOFF_VIEW,
        Permission.FIELD_UPDATE_PROGRESS, Permission.FIELD_SUBMIT_PHOTO,
        Permission.FIELD_VIEW_ZONES,
        Permission.RFI_CREATE, Permission.RFI_VIEW,
        Permission.ASSISTANT_QUERY,
    },

    Role.VIEWER: {
        Permission.PROJECT_VIEW,
        Permission.PLAN_VIEW,
        Permission.TAKEOFF_VIEW,
        Permission.FIELD_VIEW_ZONES,
        Permission.RFI_VIEW,
        Permission.REPORT_VIEW,
    },

    Role.PE_REVIEWER: {
        Permission.PE_REVIEW_QUEUE,
        Permission.PE_REVIEW_SIMULATION,
        Permission.PE_APPROVE_SIMULATION,
        Permission.PE_REJECT_SIMULATION,
        Permission.PE_CORRECT_SIMULATION,
        Permission.PE_VIEW_METRICS,
        Permission.SIMULATION_VIEW,
    },
}


def has_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())
