"""
Conduit Backend — Auth Service Layer
Prompt 3: Business logic for Auth & Organizations.

RULES:
- Service never touches DB directly — only via Repository
- Emails always to Celery queue, never synchronous
- Audit log every state change

Bliss Systems LLC — APEX Standard
"""

import re
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import (
    blacklist_refresh_token,
    check_rate_limit,
    clear_login_failures,
    get_lockout_ttl,
    get_rate_limit_ttl,
    increment_login_failure,
    is_account_locked,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_invitation_token,
    generate_password_reset_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.middleware.error_handler import (
    AccountLockedError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from app.models.auth import AuditAction, OrgRole, User
from app.modules.auth.repository import (
    AuditRepository,
    AuthRepository,
    InvitationRepository,
    OrganizationRepository,
    SessionRepository,
)
from app.modules.auth.schemas import (
    MemberResponse,
    MessageResponse,
    OrgMembershipResponse,
    OrganizationDetailResponse,
    OrganizationResponse,
    TokenResponse,
    UserResponse,
)

logger = structlog.get_logger()


class AuthService:
    """Auth business logic — orchestrates repositories and external services."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth_repo = AuthRepository(db)
        self.org_repo = OrganizationRepository(db)
        self.session_repo = SessionRepository(db)
        self.invitation_repo = InvitationRepository(db)
        self.audit_repo = AuditRepository(db)

    # ══════════════════════════════════════
    # REGISTER — Atomic user + org creation
    # ══════════════════════════════════════

    async def register(
        self,
        email: str,
        password: str,
        full_name: str,
        org_name: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Prompt 3: "POST /auth/register → user + org en transacción atómica"
        Creates user + organization + membership in single transaction.
        """
        # Check existing user
        existing = await self.auth_repo.get_by_email(email)
        if existing:
            raise ConflictError("An account with this email already exists", "EMAIL_EXISTS")

        # Create user
        hashed = hash_password(password)
        user = await self.auth_repo.create_user(email, hashed, full_name)

        # Create organization with slug
        slug = self._generate_slug(org_name)
        existing_slug = await self.org_repo.get_by_slug(slug)
        if existing_slug:
            slug = f"{slug}-{str(uuid.uuid4())[:8]}"

        # Get free plan
        free_plan = await self.org_repo.get_default_plan()
        org = await self.org_repo.create(
            name=org_name,
            slug=slug,
            plan_id=free_plan.id if free_plan else None,
        )

        # Add user as org admin
        await self.org_repo.add_member(user.id, org.id, OrgRole.ORG_ADMIN)

        # Audit
        await self.audit_repo.log(
            entity_type="user",
            entity_id=user.id,
            action=AuditAction.USER_REGISTERED.value,
            user_id=user.id,
            org_id=org.id,
            after_state={"email": email, "org_name": org_name},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Generate tokens
        tokens = await self._create_token_pair(
            user, org.id, [OrgRole.ORG_ADMIN.value],
            ip_address=ip_address, user_agent=user_agent,
        )

        # Dispatch welcome email (Celery async — never synchronous)
        try:
            from app.tasks.email_tasks import send_welcome_email
            send_welcome_email.delay(email, full_name)
        except Exception:
            logger.warning("celery_not_available", task="send_welcome_email")

        logger.info("user_registered", user_id=str(user.id), org_id=str(org.id))
        return tokens

    # ══════════════════════════════════════
    # LOGIN — Rate limited + lockout
    # ══════════════════════════════════════

    async def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        device_info: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Prompt 3: "POST /auth/login → access (15min) + refresh (30 días)"
        Rate limited: 5 attempts/15min per IP.
        Account lockout: 10 attempts → lock 1 hour.
        """
        # Rate limiting by IP
        if ip_address:
            allowed, remaining = await check_rate_limit(f"login:{ip_address}")
            if not allowed:
                ttl = await get_rate_limit_ttl(f"login:{ip_address}")
                raise RateLimitError(
                    "Too many login attempts. Please try again later.",
                    retry_after=ttl,
                )

        # Find user
        user = await self.auth_repo.get_by_email(email)
        if not user:
            raise AuthenticationError("Invalid email or password", "INVALID_CREDENTIALS")

        # Check account lockout
        if await is_account_locked(str(user.id)):
            ttl = await get_lockout_ttl(str(user.id))
            raise AccountLockedError(retry_after=ttl)

        # Check database-level lockout
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise AccountLockedError(
                retry_after=int((user.locked_until - datetime.now(timezone.utc)).total_seconds()),
            )

        # Verify password
        if not verify_password(password, user.hashed_password):
            failure_count = await increment_login_failure(str(user.id))
            await self.auth_repo.increment_failed_logins(user.id)

            if failure_count >= settings.ACCOUNT_LOCKOUT_THRESHOLD:
                lock_until = datetime.now(timezone.utc) + timedelta(
                    seconds=settings.ACCOUNT_LOCKOUT_DURATION,
                )
                await self.auth_repo.lock_account(user.id, lock_until)

                await self.audit_repo.log(
                    entity_type="user",
                    entity_id=user.id,
                    action=AuditAction.USER_LOCKED.value,
                    user_id=user.id,
                    after_state={"locked_until": lock_until.isoformat()},
                    ip_address=ip_address,
                )

            raise AuthenticationError("Invalid email or password", "INVALID_CREDENTIALS")

        # Successful login — clear failures
        await clear_login_failures(str(user.id))
        await self.auth_repo.reset_failed_logins(user.id)
        await self.auth_repo.update_last_login(user.id)

        # Get user's first org for default token
        user_orgs = await self.org_repo.get_user_orgs(user.id)
        default_org_id = user_orgs[0].org_id if user_orgs else None
        roles = [m.role.value for m in user_orgs] if user_orgs else []

        tokens = await self._create_token_pair(
            user, default_org_id, roles,
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Audit
        await self.audit_repo.log(
            entity_type="user",
            entity_id=user.id,
            action=AuditAction.USER_LOGIN.value,
            user_id=user.id,
            org_id=default_org_id,
            after_state={"device_info": device_info},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info("user_login", user_id=str(user.id))
        return tokens

    # ══════════════════════════════════════
    # REFRESH — Rotate tokens
    # ══════════════════════════════════════

    async def refresh(self, raw_refresh_token: str) -> TokenResponse:
        """
        Prompt 3: "Refresh tokens rotativos — cada uso genera nuevo token"
        Validate old token → issue new pair → revoke old.
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        session = await self.session_repo.get_by_token_hash(token_hash)

        if not session:
            raise AuthenticationError("Invalid or expired refresh token", "INVALID_REFRESH")

        user = await self.auth_repo.get_by_id(session.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive", "USER_INACTIVE")

        # Revoke old session
        await self.session_repo.revoke_session(session.id)

        # Blacklist old token in Redis
        remaining_seconds = int(
            (session.expires_at - datetime.now(timezone.utc)).total_seconds()
        )
        if remaining_seconds > 0:
            await blacklist_refresh_token(token_hash, remaining_seconds)

        # Get user orgs for new token
        user_orgs = await self.org_repo.get_user_orgs(user.id)
        default_org_id = user_orgs[0].org_id if user_orgs else None
        roles = [m.role.value for m in user_orgs] if user_orgs else []

        # Issue new pair
        return await self._create_token_pair(user, default_org_id, roles)

    # ══════════════════════════════════════
    # LOGOUT — Invalidate refresh token
    # ══════════════════════════════════════

    async def logout(
        self,
        raw_refresh_token: str,
        user_id: uuid.UUID,
    ) -> MessageResponse:
        """Prompt 3: "POST /auth/logout → invalidar refresh token (Redis blacklist)"."""
        token_hash = hash_refresh_token(raw_refresh_token)
        session = await self.session_repo.get_by_token_hash(token_hash)

        if session:
            await self.session_repo.revoke_session(session.id)

            remaining = int(
                (session.expires_at - datetime.now(timezone.utc)).total_seconds()
            )
            if remaining > 0:
                await blacklist_refresh_token(token_hash, remaining)

        await self.audit_repo.log(
            entity_type="user",
            entity_id=user_id,
            action=AuditAction.USER_LOGOUT.value,
            user_id=user_id,
        )

        return MessageResponse(message="Successfully logged out")

    # ══════════════════════════════════════
    # FORGOT PASSWORD — OTP via Celery
    # ══════════════════════════════════════

    async def forgot_password(self, email: str) -> MessageResponse:
        """
        Prompt 3: "POST /auth/forgot-password → email con link OTP (Celery async)"
        Always returns success to prevent email enumeration.
        """
        user = await self.auth_repo.get_by_email(email)

        if user:
            token = generate_password_reset_token()
            # Store reset token as an invitation-type record (reuse mechanism)
            expires = datetime.now(timezone.utc) + timedelta(hours=1)
            await self.invitation_repo.create(
                email=email,
                token=token,
                org_id=uuid.UUID(int=0),  # Placeholder for password reset
                role=OrgRole.ORG_MEMBER,
                invited_by=user.id,
                expires_at=expires,
            )

            # Dispatch email via Celery
            try:
                from app.tasks.email_tasks import send_password_reset_email
                send_password_reset_email.delay(email, token)
            except Exception:
                logger.warning("celery_not_available", task="send_password_reset_email")

        # Always return success — prevent email enumeration
        return MessageResponse(
            message="If an account exists with this email, a reset link has been sent."
        )

    # ══════════════════════════════════════
    # RESET PASSWORD — Validate OTP
    # ══════════════════════════════════════

    async def reset_password(
        self,
        token: str,
        new_password: str,
        ip_address: str | None = None,
    ) -> MessageResponse:
        """Prompt 3: "POST /auth/reset-password → cambiar password con token"."""
        invitation = await self.invitation_repo.get_by_token(token)
        if not invitation:
            raise AuthenticationError("Invalid or expired reset token", "INVALID_RESET_TOKEN")

        user = await self.auth_repo.get_by_email(invitation.email)
        if not user:
            raise NotFoundError("User")

        # Update password
        hashed = hash_password(new_password)
        await self.auth_repo.update_password(user.id, hashed)

        # Mark token as used
        await self.invitation_repo.mark_accepted(invitation.id)

        # Revoke all existing sessions
        await self.session_repo.revoke_all_user_sessions(user.id)

        # Audit
        await self.audit_repo.log(
            entity_type="user",
            entity_id=user.id,
            action=AuditAction.USER_PASSWORD_CHANGED.value,
            user_id=user.id,
            ip_address=ip_address,
        )

        return MessageResponse(message="Password has been reset successfully")

    # ══════════════════════════════════════
    # GET ME — Profile with org memberships
    # ══════════════════════════════════════

    async def get_me(self, user: User) -> UserResponse:
        """Prompt 3: "GET /auth/me → perfil + orgs + roles"."""
        memberships = await self.org_repo.get_user_orgs(user.id)

        org_responses = []
        for m in memberships:
            org = await self.org_repo.get_by_id(m.org_id)
            if org:
                org_responses.append(
                    OrgMembershipResponse(
                        org_id=org.id,
                        org_name=org.name,
                        role=m.role.value,
                    )
                )

        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            is_active=user.is_active,
            created_at=user.created_at,
            organizations=org_responses,
        )

    # ══════════════════════════════════════
    # ORGANIZATION MANAGEMENT
    # ══════════════════════════════════════

    async def create_organization(
        self,
        name: str,
        user: User,
    ) -> OrganizationResponse:
        """Create a new organization and add user as admin."""
        slug = self._generate_slug(name)
        existing = await self.org_repo.get_by_slug(slug)
        if existing:
            slug = f"{slug}-{str(uuid.uuid4())[:8]}"

        free_plan = await self.org_repo.get_default_plan()
        org = await self.org_repo.create(
            name=name,
            slug=slug,
            plan_id=free_plan.id if free_plan else None,
        )
        await self.org_repo.add_member(user.id, org.id, OrgRole.ORG_ADMIN)

        await self.audit_repo.log(
            entity_type="organization",
            entity_id=org.id,
            action=AuditAction.ORG_CREATED.value,
            user_id=user.id,
            org_id=org.id,
            after_state={"name": name, "slug": slug},
        )

        return OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            logo_url=org.logo_url,
            member_count=1,
            plan_name=free_plan.display_name if free_plan else None,
            created_at=org.created_at,
        )

    async def get_my_organization(
        self,
        org_id: uuid.UUID,
        user: User,
    ) -> OrganizationDetailResponse:
        """Get current org with members and stats."""
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization")

        members = await self.org_repo.get_members(org_id)
        member_responses = []
        for m in members:
            member_user = await self.auth_repo.get_by_id(m.user_id)
            if member_user:
                member_responses.append(
                    MemberResponse(
                        id=m.id,
                        user_id=m.user_id,
                        email=member_user.email,
                        full_name=member_user.full_name,
                        role=m.role.value,
                        joined_at=m.created_at,
                    )
                )

        plan_name = org.plan.display_name if org.plan else None

        return OrganizationDetailResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            logo_url=org.logo_url,
            member_count=len(members),
            plan_name=plan_name,
            created_at=org.created_at,
            members=member_responses,
            preferred_suppliers=org.preferred_suppliers,
        )

    async def update_organization(
        self,
        org_id: uuid.UUID,
        user: User,
        name: str | None = None,
        logo_url: str | None = None,
    ) -> MessageResponse:
        """Update org details. Requires ORG_ADMIN."""
        updates = {}
        if name is not None:
            updates["name"] = name
        if logo_url is not None:
            updates["logo_url"] = logo_url

        if not updates:
            raise ValidationError("No fields to update")

        org = await self.org_repo.get_by_id(org_id)
        before = {"name": org.name, "logo_url": org.logo_url} if org else {}

        await self.org_repo.update(org_id, **updates)

        await self.audit_repo.log(
            entity_type="organization",
            entity_id=org_id,
            action=AuditAction.ORG_UPDATED.value,
            user_id=user.id,
            org_id=org_id,
            before_state=before,
            after_state=updates,
        )

        return MessageResponse(message="Organization updated successfully")

    # ══════════════════════════════════════
    # INVITATION FLOW
    # ══════════════════════════════════════

    async def invite_member(
        self,
        org_id: uuid.UUID,
        email: str,
        role: str,
        inviter: User,
    ) -> MessageResponse:
        """Prompt 3: "POST /organizations/invite → invitar por email (Celery)"."""
        # Check if already a member
        existing_user = await self.auth_repo.get_by_email(email)
        if existing_user:
            existing_member = await self.org_repo.get_member(existing_user.id, org_id)
            if existing_member:
                raise ConflictError("User is already a member of this organization")

        # Check for pending invitation
        pending = await self.invitation_repo.get_pending_for_email(email, org_id)
        if pending:
            raise ConflictError("An invitation is already pending for this email")

        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization")

        token = generate_invitation_token()
        expires = datetime.now(timezone.utc) + timedelta(days=7)

        await self.invitation_repo.create(
            email=email,
            token=token,
            org_id=org_id,
            role=OrgRole(role),
            invited_by=inviter.id,
            expires_at=expires,
        )

        await self.audit_repo.log(
            entity_type="invitation",
            entity_id=uuid.uuid4(),  # Invitation tracking
            action=AuditAction.ORG_MEMBER_INVITED.value,
            user_id=inviter.id,
            org_id=org_id,
            after_state={"email": email, "role": role},
        )

        # Dispatch email via Celery
        try:
            from app.tasks.email_tasks import send_invitation_email
            send_invitation_email.delay(email, org.name, token, inviter.full_name)
        except Exception:
            logger.warning("celery_not_available", task="send_invitation_email")

        return MessageResponse(message=f"Invitation sent to {email}")

    async def accept_invitation(
        self,
        token: str,
        user: User | None = None,
    ) -> MessageResponse:
        """Prompt 3: "POST /organizations/accept/{token} → aceptar invitación"."""
        invitation = await self.invitation_repo.get_by_token(token)
        if not invitation:
            raise AuthenticationError("Invalid or expired invitation", "INVALID_INVITATION")

        # Find or create user
        target_user = await self.auth_repo.get_by_email(invitation.email)
        if not target_user and user:
            target_user = user
        elif not target_user:
            raise NotFoundError("User")

        # Add to org
        existing = await self.org_repo.get_member(target_user.id, invitation.org_id)
        if existing:
            raise ConflictError("Already a member of this organization")

        await self.org_repo.add_member(
            target_user.id,
            invitation.org_id,
            invitation.role,
        )
        await self.invitation_repo.mark_accepted(invitation.id)

        await self.audit_repo.log(
            entity_type="organization_member",
            entity_id=target_user.id,
            action=AuditAction.ORG_MEMBER_JOINED.value,
            user_id=target_user.id,
            org_id=invitation.org_id,
            after_state={"role": invitation.role.value},
        )

        return MessageResponse(message="Invitation accepted successfully")

    async def get_members(self, org_id: uuid.UUID) -> list[MemberResponse]:
        """List all org members with their roles."""
        members = await self.org_repo.get_members(org_id)
        responses = []
        for m in members:
            user = await self.auth_repo.get_by_id(m.user_id)
            if user:
                responses.append(
                    MemberResponse(
                        id=m.id,
                        user_id=m.user_id,
                        email=user.email,
                        full_name=user.full_name,
                        role=m.role.value,
                        joined_at=m.created_at,
                    )
                )
        return responses

    async def update_member_role(
        self,
        org_id: uuid.UUID,
        member_id: uuid.UUID,
        new_role: str,
        actor: User,
    ) -> MessageResponse:
        """Change a member's role. Requires ORG_ADMIN."""
        member = await self.org_repo.get_member_by_id(member_id, org_id)
        if not member:
            raise NotFoundError("Member")

        old_role = member.role.value

        # Prevent demoting last admin
        if old_role in ("ORG_ADMIN", "SUPER_ADMIN") and new_role not in ("ORG_ADMIN", "SUPER_ADMIN"):
            admin_count = await self.org_repo.count_admins(org_id)
            if admin_count <= 1:
                raise ValidationError("Cannot demote the last admin of the organization")

        await self.org_repo.update_member_role(member_id, OrgRole(new_role))

        await self.audit_repo.log(
            entity_type="organization_member",
            entity_id=member.user_id,
            action=AuditAction.ORG_MEMBER_ROLE_CHANGED.value,
            user_id=actor.id,
            org_id=org_id,
            before_state={"role": old_role},
            after_state={"role": new_role},
        )

        return MessageResponse(message=f"Role updated to {new_role}")

    async def remove_member(
        self,
        org_id: uuid.UUID,
        member_id: uuid.UUID,
        actor: User,
    ) -> MessageResponse:
        """Remove member from org. Cannot remove last admin."""
        member = await self.org_repo.get_member_by_id(member_id, org_id)
        if not member:
            raise NotFoundError("Member")

        # Prevent removing last admin
        if member.role in (OrgRole.ORG_ADMIN, OrgRole.SUPER_ADMIN):
            admin_count = await self.org_repo.count_admins(org_id)
            if admin_count <= 1:
                raise ValidationError("Cannot remove the last admin of the organization")

        await self.org_repo.remove_member(member_id)

        await self.audit_repo.log(
            entity_type="organization_member",
            entity_id=member.user_id,
            action=AuditAction.ORG_MEMBER_REMOVED.value,
            user_id=actor.id,
            org_id=org_id,
            before_state={"role": member.role.value},
        )

        return MessageResponse(message="Member removed successfully")

    # ══════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════

    async def _create_token_pair(
        self,
        user: User,
        org_id: uuid.UUID | None,
        roles: list[str],
        device_info: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """Create access + refresh token pair, store session in DB."""
        access_token = create_access_token(user.id, org_id, roles)
        raw_refresh, refresh_hash = create_refresh_token(user.id)

        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        )

        await self.session_repo.create_session(
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            expires_at=expires_at,
            device_info=device_info,
            last_ip=ip_address,
            user_agent=user_agent,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    def _generate_slug(name: str) -> str:
        """Generate URL-safe slug from org name."""
        slug = name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug[:100]
