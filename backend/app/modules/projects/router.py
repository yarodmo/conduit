"""
Conduit Backend — Projects Router
Sprint 2: 9 endpoints (CRUD + Team Membership)

Endpoints:
  POST   /projects                        → create project
  GET    /projects                        → list projects (scoped)
  GET    /projects/{id}                   → get detail + members
  PATCH  /projects/{id}                   → update project
  DELETE /projects/{id}                   → soft-delete project
  GET    /projects/{id}/members           → list team members
  POST   /projects/{id}/members           → add team member
  PATCH  /projects/{id}/members/{uid}     → update member role
  DELETE /projects/{id}/members/{uid}     → remove team member

All endpoints require X-Organization-ID header → tenant isolation.

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user, get_org_membership
from app.models.auth import Organization, OrganizationMember, User
from app.modules.projects.schemas import (
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectMemberAddRequest,
    ProjectMemberResponse,
    ProjectMemberUpdateRoleRequest,
    ProjectResponse,
)
from app.modules.projects.service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


def _get_service(db: AsyncSession) -> ProjectService:
    return ProjectService(db)


# ══════════════════════════════════════
# CRUD ENDPOINTS
# ══════════════════════════════════════

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Create a new project within the current organization.
    Creator is automatically added as OWNER.
    Requires: PROJECT_CREATE permission (ORG_ADMIN, ORG_MEMBER).
    """
    svc = _get_service(db)
    return await svc.create_project(
        payload=payload,
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ProjectListResponse:
    """
    List projects in the current organization.
    ORG_ADMIN sees all projects; others see only their assigned projects.
    """
    svc = _get_service(db)
    return await svc.list_projects(
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
    )


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailResponse:
    """
    Get full project detail including team members.
    Non-admin must be a project member to view.
    """
    svc = _get_service(db)
    return await svc.get_project(
        project_id=project_id,
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Update project details.
    Allowed: ORG_ADMIN, project OWNER, PROJECT_MANAGER.
    """
    from app.modules.projects.schemas import ProjectUpdateRequest as _PUR
    svc = _get_service(db)
    return await svc.update_project(
        project_id=project_id,
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
        payload=payload,
    )


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
async def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Soft-delete a project.
    Allowed: ORG_ADMIN, project OWNER only.
    """
    svc = _get_service(db)
    return await svc.delete_project(
        project_id=project_id,
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
    )


# ══════════════════════════════════════
# TEAM MEMBERSHIP ENDPOINTS
# ══════════════════════════════════════

@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse])
async def list_members(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectMemberResponse]:
    """List all team members of a project (single JOIN query)."""
    svc = _get_service(db)
    return await svc.list_members(
        project_id=project_id,
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
    )


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: uuid.UUID,
    payload: ProjectMemberAddRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ProjectMemberResponse:
    """
    Add a user to the project team.
    Allowed: ORG_ADMIN, project OWNER, PROJECT_MANAGER.
    """
    svc = _get_service(db)
    return await svc.add_member(
        project_id=project_id,
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
        target_user_id=payload.user_id,
        role=payload.role,
    )


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberResponse)
async def update_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ProjectMemberUpdateRoleRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ProjectMemberResponse:
    """
    Update a team member's role (cannot set to OWNER).
    Allowed: ORG_ADMIN, project OWNER, PROJECT_MANAGER.
    """
    svc = _get_service(db)
    return await svc.update_member_role(
        project_id=project_id,
        user_id=user_id,
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
        new_role=payload.role,
    )


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_200_OK)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Remove a user from the project team.
    Cannot remove the OWNER. Allowed: ORG_ADMIN, OWNER, PROJECT_MANAGER.
    """
    svc = _get_service(db)
    return await svc.remove_member(
        project_id=project_id,
        user_id=user_id,
        org_id=org.id,
        org_role=membership.role,
        current_user_id=user.id,
    )
