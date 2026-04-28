"""
Conduit Backend — Auth Repository Layer
Prompt 3: "Repository pattern estricto: service nunca toca DB directamente"

All database operations isolated here. Services call these methods only.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import (
    AuditLog,
    Invitation,
    Organization,
    OrganizationMember,
    OrgRole,
    SubscriptionPlan,
    User,
    UserSession,
)


class AuthRepository:
    """User-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(
        self,
        email: str,
        hashed_password: str,
        full_name: str,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.email == email,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(
            select(User).where(
                User.id == user_id,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )

    async def increment_failed_logins(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(User.failed_login_attempts).where(User.id == user_id)
        )
        current = result.scalar_one() or 0
        new_count = current + 1

        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=new_count)
        )
        return new_count

    async def reset_failed_logins(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=0, locked_until=None)
        )

    async def lock_account(self, user_id: uuid.UUID, until: datetime) -> None:
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(locked_until=until)
        )

    async def update_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(hashed_password=hashed_password)
        )


class OrganizationRepository:
    """Organization-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        name: str,
        slug: str,
        plan_id: uuid.UUID | None = None,
    ) -> Organization:
        org = Organization(name=name, slug=slug, plan_id=plan_id)
        self.db.add(org)
        await self.db.flush()
        return org

    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None:
        result = await self.db.execute(
            select(Organization).where(
                Organization.id == org_id,
                Organization.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self.db.execute(
            select(Organization).where(
                Organization.slug == slug,
                Organization.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        org_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        await self.db.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(**kwargs)
        )

    async def add_member(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        role: OrgRole,
    ) -> OrganizationMember:
        member = OrganizationMember(
            user_id=user_id,
            org_id=org_id,
            role=role,
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def get_member(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> OrganizationMember | None:
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.org_id == org_id,
                OrganizationMember.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_member_by_id(
        self,
        member_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> OrganizationMember | None:
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.id == member_id,
                OrganizationMember.org_id == org_id,
                OrganizationMember.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_members(self, org_id: uuid.UUID) -> list[OrganizationMember]:
        result = await self.db.execute(
            select(OrganizationMember)
            .where(
                OrganizationMember.org_id == org_id,
                OrganizationMember.deleted_at.is_(None),
            )
            .order_by(OrganizationMember.created_at)
        )
        return list(result.scalars().all())

    async def update_member_role(
        self,
        member_id: uuid.UUID,
        role: OrgRole,
    ) -> None:
        await self.db.execute(
            update(OrganizationMember)
            .where(OrganizationMember.id == member_id)
            .values(role=role)
        )

    async def remove_member(self, member_id: uuid.UUID) -> None:
        """Soft delete organization member."""
        await self.db.execute(
            update(OrganizationMember)
            .where(OrganizationMember.id == member_id)
            .values(deleted_at=datetime.now(timezone.utc))
        )

    async def count_admins(self, org_id: uuid.UUID) -> int:
        """Count active admins in org — prevent removing last admin."""
        result = await self.db.execute(
            select(func.count(OrganizationMember.id)).where(
                OrganizationMember.org_id == org_id,
                OrganizationMember.role.in_([OrgRole.ORG_ADMIN, OrgRole.SUPER_ADMIN]),
                OrganizationMember.deleted_at.is_(None),
            )
        )
        return result.scalar_one() or 0

    async def get_user_orgs(self, user_id: uuid.UUID) -> list[OrganizationMember]:
        """Get all organizations a user belongs to."""
        result = await self.db.execute(
            select(OrganizationMember)
            .where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_default_plan(self) -> SubscriptionPlan | None:
        """Get the free plan for new organizations."""
        result = await self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.name == "free",
                SubscriptionPlan.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()


class SessionRepository:
    """User session / refresh token operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        device_info: str | None = None,
        last_ip: str | None = None,
        user_agent: str | None = None,
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            device_info=device_info,
            last_ip=last_ip,
            user_agent=user_agent,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == token_hash,
                UserSession.is_revoked.is_(False),
                UserSession.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_session(self, session_id: uuid.UUID) -> None:
        await self.db.execute(
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(is_revoked=True)
        )

    async def revoke_all_user_sessions(self, user_id: uuid.UUID) -> None:
        """Revoke all sessions for a user (password reset scenario)."""
        await self.db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )


class InvitationRepository:
    """Invitation operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        email: str,
        token: str,
        org_id: uuid.UUID,
        role: OrgRole,
        invited_by: uuid.UUID,
        expires_at: datetime,
    ) -> Invitation:
        invitation = Invitation(
            email=email,
            token=token,
            org_id=org_id,
            role=role,
            invited_by=invited_by,
            expires_at=expires_at,
        )
        self.db.add(invitation)
        await self.db.flush()
        return invitation

    async def get_by_token(self, token: str) -> Invitation | None:
        result = await self.db.execute(
            select(Invitation).where(
                Invitation.token == token,
                Invitation.accepted_at.is_(None),
                Invitation.expires_at > datetime.now(timezone.utc),
                Invitation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def mark_accepted(self, invitation_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Invitation)
            .where(Invitation.id == invitation_id)
            .values(accepted_at=datetime.now(timezone.utc))
        )

    async def get_pending_for_email(
        self, email: str, org_id: uuid.UUID,
    ) -> Invitation | None:
        """Check for existing pending invitation."""
        result = await self.db.execute(
            select(Invitation).where(
                Invitation.email == email,
                Invitation.org_id == org_id,
                Invitation.accepted_at.is_(None),
                Invitation.expires_at > datetime.now(timezone.utc),
                Invitation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


class AuditRepository:
    """
    Audit log operations — APPEND-ONLY.
    NO update or delete methods. Legal evidence trail.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        user_id: uuid.UUID | None = None,
        org_id: uuid.UUID | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        """Append an immutable audit record. No updates. No deletes."""
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            user_id=user_id,
            org_id=org_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry
