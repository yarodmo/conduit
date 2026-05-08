"""
Conduit Backend — Projects Service
Sprint 2: Business logic, RBAC enforcement, audit logging

RBAC rules enforced here (not in router):
  - PROJECT_CREATE  → ORG_ADMIN, ORG_MEMBER
  - PROJECT_READ    → all org members
  - PROJECT_UPDATE  → ORG_ADMIN, PROJECT_MANAGER, OWNER of project
  - PROJECT_DELETE  → ORG_ADMIN, OWNER of project
  - PROJECT_MANAGE_MEMBERS → ORG_ADMIN, PROJECT_MANAGER, OWNER

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime, timezone

import structlog

from app.core.permissions import Permission, Role, has_permission
from app.models.auth import AuditLog, OrgRole
from app.models.projects import ProjectMember, ProjectMemberRole
from app.modules.projects.repository import ProjectMemberRepository, ProjectRepository
from app.modules.projects.schemas import (
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from fastapi import HTTPException, status

logger = structlog.get_logger()


class ProjectService:
    """
    Business logic for Projects + Team Membership.
    Receives current_user info from the router dependency.
    """

    def __init__(self, db) -> None:
        self.db = db
        self.repo = ProjectRepository(db)
        self.member_repo = ProjectMemberRepository(db)

    # ══════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════

    def _check_org_permission(self, org_role: OrgRole, permission: Permission) -> None:
        """Raise 403 if the org-level role lacks permission."""
        role = Role(org_role.value)
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {org_role.value} lacks permission: {permission.value}",
            )

    async def _get_project_or_404(
        self, project_id: uuid.UUID, org_id: uuid.UUID,
    ):
        project = await self.repo.get_by_id(project_id, org_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )
        return project

    async def _get_project_member_role(
        self, project_id: uuid.UUID, user_id: uuid.UUID,
    ) -> ProjectMemberRole | None:
        m = await self.member_repo.get_member(project_id, user_id)
        return m.role if m else None

    async def _write_audit(
        self,
        *,
        action: str,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        before: dict | None = None,
        after: dict | None = None,
    ) -> None:
        log = AuditLog(
            entity_type="project",
            entity_id=entity_id,
            action=action,
            user_id=user_id,
            org_id=org_id,
            before_state=before,
            after_state=after,
        )
        self.db.add(log)
        await self.db.flush()

    # ══════════════════════════════════════
    # CRUD
    # ══════════════════════════════════════

    async def create_project(
        self,
        *,
        payload: ProjectCreateRequest,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
    ) -> ProjectResponse:
        self._check_org_permission(org_role, Permission.PROJECT_CREATE)

        project = await self.repo.create(
            org_id=org_id,
            name=payload.name,
            description=payload.description,
            project_type=payload.type,
            complexity=payload.complexity,
            address=payload.address,
            city=payload.city,
            state=payload.state,
            zip_code=payload.zip_code,
            general_contractor=payload.general_contractor,
            owner_name=payload.owner_name,
            creator_user_id=current_user_id,
        )

        await self._write_audit(
            action="project.created",
            entity_id=project.id,
            user_id=current_user_id,
            org_id=org_id,
            after={"name": project.name, "type": project.type.value},
        )

        logger.info("project_created", project_id=str(project.id), user=str(current_user_id))
        return ProjectResponse.model_validate(project)

    async def list_projects(
        self,
        *,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
    ) -> ProjectListResponse:
        self._check_org_permission(org_role, Permission.PROJECT_READ)

        # ORG_ADMIN sees all; other roles see only their assigned projects
        if org_role == OrgRole.ORG_ADMIN:
            projects = await self.repo.list_for_org(org_id)
            items = [ProjectResponse.model_validate(p) for p in projects]
        else:
            rows = await self.repo.list_for_user_in_org(current_user_id, org_id)
            items = [ProjectResponse.model_validate(p) for p, _ in rows]

        return ProjectListResponse(projects=items, total=len(items))

    async def get_project(
        self,
        *,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
    ) -> ProjectDetailResponse:
        self._check_org_permission(org_role, Permission.PROJECT_READ)
        project = await self._get_project_or_404(project_id, org_id)

        # Non-admin must be a project member to see detail
        if org_role != OrgRole.ORG_ADMIN:
            member_role = await self._get_project_member_role(project_id, current_user_id)
            if member_role is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not a member of this project",
                )

        # Fetch members via single JOIN
        member_rows = await self.member_repo.get_members_with_users(project_id)
        members = [
            ProjectMemberResponse(
                id=m.id,
                user_id=m.user_id,
                email=u.email,
                full_name=u.full_name,
                role=m.role.value,
                joined_at=m.created_at,
            )
            for m, u in member_rows
        ]

        base_project = ProjectResponse.model_validate(project)
        return ProjectDetailResponse(
            **base_project.model_dump(),
            members=members
        )

    async def update_project(
        self,
        *,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
        payload: ProjectUpdateRequest,
    ) -> ProjectResponse:
        project = await self._get_project_or_404(project_id, org_id)

        # ORG_ADMIN OR project OWNER/MANAGER can update
        if org_role != OrgRole.ORG_ADMIN:
            member_role = await self._get_project_member_role(project_id, current_user_id)
            if member_role not in (ProjectMemberRole.OWNER, ProjectMemberRole.PROJECT_MANAGER):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only project OWNER, PROJECT_MANAGER, or ORG_ADMIN can update",
                )

        before = {"name": project.name, "description": project.description}
        fields = {k: v for k, v in payload.model_dump().items() if v is not None}
        updated = await self.repo.update(project_id, org_id, **fields)

        await self._write_audit(
            action="project.updated",
            entity_id=project_id,
            user_id=current_user_id,
            org_id=org_id,
            before=before,
            after=fields,
        )
        return ProjectResponse.model_validate(updated)

    async def delete_project(
        self,
        *,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
    ) -> dict:
        await self._get_project_or_404(project_id, org_id)

        if org_role != OrgRole.ORG_ADMIN:
            member_role = await self._get_project_member_role(project_id, current_user_id)
            if member_role != ProjectMemberRole.OWNER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only project OWNER or ORG_ADMIN can delete",
                )

        deleted = await self.repo.soft_delete(project_id, org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Project not found")

        await self._write_audit(
            action="project.deleted",
            entity_id=project_id,
            user_id=current_user_id,
            org_id=org_id,
        )
        logger.info("project_deleted", project_id=str(project_id), user=str(current_user_id))
        return {"message": "Project deleted"}

    # ══════════════════════════════════════
    # TEAM MEMBERSHIP
    # ══════════════════════════════════════

    async def add_member(
        self,
        *,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
        target_user_id: uuid.UUID,
        role: str,
    ) -> ProjectMemberResponse:
        self._check_org_permission(org_role, Permission.PROJECT_MANAGE_MEMBERS)
        await self._get_project_or_404(project_id, org_id)

        # Enforce: non-admin must be OWNER or PROJECT_MANAGER
        if org_role != OrgRole.ORG_ADMIN:
            caller_role = await self._get_project_member_role(project_id, current_user_id)
            if caller_role not in (ProjectMemberRole.OWNER, ProjectMemberRole.PROJECT_MANAGER):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only OWNER, PROJECT_MANAGER, or ORG_ADMIN can manage members",
                )

        # Duplicate check
        existing = await self.member_repo.get_member(project_id, target_user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this project",
            )

        member = await self.member_repo.add_member(
            project_id=project_id,
            user_id=target_user_id,
            role=ProjectMemberRole(role),
        )

        await self._write_audit(
            action="project.member_added",
            entity_id=project_id,
            user_id=current_user_id,
            org_id=org_id,
            after={"target_user": str(target_user_id), "role": role},
        )

        # Fetch user for email/name in response
        from sqlalchemy import select
        from app.models.auth import User
        result = await self.db.execute(select(User).where(User.id == target_user_id))
        user = result.scalar_one_or_none()

        return ProjectMemberResponse(
            id=member.id,
            user_id=member.user_id,
            email=user.email if user else "",
            full_name=user.full_name if user else "",
            role=member.role.value,
            joined_at=member.created_at,
        )

    async def update_member_role(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
        new_role: str,
    ) -> ProjectMemberResponse:
        self._check_org_permission(org_role, Permission.PROJECT_MANAGE_MEMBERS)
        await self._get_project_or_404(project_id, org_id)

        if org_role != OrgRole.ORG_ADMIN:
            caller_role = await self._get_project_member_role(project_id, current_user_id)
            if caller_role not in (ProjectMemberRole.OWNER, ProjectMemberRole.PROJECT_MANAGER):
                raise HTTPException(status_code=403, detail="Insufficient project role")

        updated = await self.member_repo.update_role(
            project_id, user_id, ProjectMemberRole(new_role)
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Member not found")

        from sqlalchemy import select
        from app.models.auth import User
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        return ProjectMemberResponse(
            id=updated.id,
            user_id=updated.user_id,
            email=user.email if user else "",
            full_name=user.full_name if user else "",
            role=updated.role.value,
            joined_at=updated.created_at,
        )

    async def remove_member(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
    ) -> dict:
        self._check_org_permission(org_role, Permission.PROJECT_MANAGE_MEMBERS)
        await self._get_project_or_404(project_id, org_id)

        if org_role != OrgRole.ORG_ADMIN:
            caller_role = await self._get_project_member_role(project_id, current_user_id)
            if caller_role not in (ProjectMemberRole.OWNER, ProjectMemberRole.PROJECT_MANAGER):
                raise HTTPException(status_code=403, detail="Insufficient project role")

        removed = await self.member_repo.remove_member(project_id, user_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove OWNER or member not found",
            )

        await self._write_audit(
            action="project.member_removed",
            entity_id=project_id,
            user_id=current_user_id,
            org_id=org_id,
            after={"removed_user": str(user_id)},
        )
        return {"message": "Member removed"}

    async def list_members(
        self,
        *,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        org_role: OrgRole,
        current_user_id: uuid.UUID,
    ) -> list[ProjectMemberResponse]:
        self._check_org_permission(org_role, Permission.PROJECT_READ)
        await self._get_project_or_404(project_id, org_id)

        rows = await self.member_repo.get_members_with_users(project_id)
        return [
            ProjectMemberResponse(
                id=m.id,
                user_id=m.user_id,
                email=u.email,
                full_name=u.full_name,
                role=m.role.value,
                joined_at=m.created_at,
            )
            for m, u in rows
        ]
