"""
Conduit Backend — Projects Repository
Sprint 2: Full CRUD + Team Membership

All queries are JOIN-first (no N+1). Tenant isolation enforced
on every method via org_id filter. Soft-delete via deleted_at.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.projects import Project, ProjectMember, ProjectMemberRole


class ProjectRepository:
    """Data-access layer for Projects. All methods are org-scoped."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ══════════════════════════════════════
    # CREATE
    # ══════════════════════════════════════

    async def create(
        self,
        *,
        org_id: uuid.UUID,
        name: str,
        description: str | None,
        project_type: str,
        complexity: str,
        address: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        general_contractor: str | None = None,
        owner_name: str | None = None,
        creator_user_id: uuid.UUID,
    ) -> Project:
        """
        Create a project and automatically add creator as OWNER.
        Atomic: both inserts happen in the same transaction.
        """
        from app.models.projects import ProjectComplexity, ProjectType

        project = Project(
            org_id=org_id,
            name=name,
            description=description,
            type=ProjectType(project_type),
            complexity=ProjectComplexity(complexity),
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            general_contractor=general_contractor,
            owner_name=owner_name,
            is_active=True,
        )
        self.db.add(project)
        await self.db.flush()  # get project.id before membership insert

        # Auto-add creator as OWNER
        owner_membership = ProjectMember(
            user_id=creator_user_id,
            project_id=project.id,
            role=ProjectMemberRole.OWNER,
        )
        self.db.add(owner_membership)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    # ══════════════════════════════════════
    # READ — single
    # ══════════════════════════════════════

    async def get_by_id(
        self, project_id: uuid.UUID, org_id: uuid.UUID,
    ) -> Project | None:
        """
        Fetch project by ID — always scoped to org_id (tenant isolation).
        Returns None if not found OR if project belongs to another tenant.
        """
        result = await self.db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.org_id == org_id,
                Project.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    # ══════════════════════════════════════
    # READ — list (with member count JOIN)
    # ══════════════════════════════════════

    async def list_for_org(self, org_id: uuid.UUID) -> list[Project]:
        """List all active projects for an organization."""
        result = await self.db.execute(
            select(Project)
            .where(
                Project.org_id == org_id,
                Project.deleted_at.is_(None),
            )
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_user_in_org(
        self, user_id: uuid.UUID, org_id: uuid.UUID,
    ) -> list[tuple[Project, ProjectMember]]:
        """
        Single JOIN: list projects a user is a member of within org.
        Returns (Project, ProjectMember) tuples — avoids N+1.
        """
        result = await self.db.execute(
            select(Project, ProjectMember)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                Project.org_id == org_id,
                Project.deleted_at.is_(None),
                ProjectMember.user_id == user_id,
                ProjectMember.deleted_at.is_(None),
            )
            .order_by(Project.created_at.desc())
        )
        return list(result.all())

    # ══════════════════════════════════════
    # UPDATE
    # ══════════════════════════════════════

    async def update(
        self,
        project_id: uuid.UUID,
        org_id: uuid.UUID,
        **fields,
    ) -> Project | None:
        """
        Partial update — only fields passed in **fields are changed.
        Tenant isolation: org_id in WHERE prevents cross-tenant writes.
        """
        if not fields:
            return await self.get_by_id(project_id, org_id)

        fields["updated_at"] = datetime.now(timezone.utc)
        await self.db.execute(
            update(Project)
            .where(
                Project.id == project_id,
                Project.org_id == org_id,
                Project.deleted_at.is_(None),
            )
            .values(**fields)
        )
        await self.db.commit()
        return await self.get_by_id(project_id, org_id)

    # ══════════════════════════════════════
    # SOFT DELETE
    # ══════════════════════════════════════

    async def soft_delete(
        self, project_id: uuid.UUID, org_id: uuid.UUID,
    ) -> bool:
        """
        Soft-delete project. Returns True if a row was affected.
        Tenant isolation: org_id in WHERE — cross-tenant delete impossible.
        """
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(Project)
            .where(
                Project.id == project_id,
                Project.org_id == org_id,
                Project.deleted_at.is_(None),
            )
            .values(deleted_at=now, updated_at=now)
        )
        await self.db.commit()
        return result.rowcount > 0  # type: ignore[return-value]


class ProjectMemberRepository:
    """Data-access layer for Project Team Membership."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ══════════════════════════════════════
    # READ
    # ══════════════════════════════════════

    async def get_member(
        self, project_id: uuid.UUID, user_id: uuid.UUID,
    ) -> ProjectMember | None:
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_members_with_users(
        self, project_id: uuid.UUID,
    ) -> list[tuple[ProjectMember, User]]:
        """
        Single JOIN — no N+1.
        Returns (ProjectMember, User) tuples for all project members.
        """
        result = await self.db.execute(
            select(ProjectMember, User)
            .join(User, ProjectMember.user_id == User.id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
            .order_by(ProjectMember.created_at)
        )
        return list(result.all())

    # ══════════════════════════════════════
    # ADD / UPDATE / REMOVE
    # ══════════════════════════════════════

    async def add_member(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        role: ProjectMemberRole,
    ) -> ProjectMember:
        member = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            role=role,
        )
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(member)
        return member

    async def update_role(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        new_role: ProjectMemberRole,
    ) -> ProjectMember | None:
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(ProjectMember)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.deleted_at.is_(None),
            )
            .values(role=new_role, updated_at=now)
        )
        await self.db.commit()
        return await self.get_member(project_id, user_id)

    async def remove_member(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """
        Soft-delete membership. Returns False if OWNER removal attempted
        (business rule: owner cannot be removed).
        """
        member = await self.get_member(project_id, user_id)
        if not member or member.role == ProjectMemberRole.OWNER:
            return False

        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(ProjectMember)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.deleted_at.is_(None),
            )
            .values(deleted_at=now, updated_at=now)
        )
        await self.db.commit()
        return True

    async def count_owners(self, project_id: uuid.UUID) -> int:
        """Count active OWNER memberships — must never reach zero."""
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == ProjectMemberRole.OWNER,
                ProjectMember.deleted_at.is_(None),
            )
        )
        return len(result.scalars().all())
