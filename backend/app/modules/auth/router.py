"""
Conduit Backend — Auth Router
Prompt 3: All 15 endpoints for Auth & Organizations.

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user, get_org_membership
from app.models.auth import Organization, OrganizationMember, User
from app.modules.auth.schemas import (
    CreateOrganizationRequest,
    ForgotPasswordRequest,
    InviteRequest,
    LoginRequest,
    MemberResponse,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateMemberRequest,
    UpdateOrganizationRequest,
    UserResponse,
    OrganizationDetailResponse,
    OrganizationResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter()


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


# ══════════════════════════════════════
# AUTH ENDPOINTS
# ══════════════════════════════════════

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    data: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Register new user + organization in atomic transaction.
    Prompt 3: "POST /auth/register → user + org en transacción atómica"
    """
    service = AuthService(db)
    return await service.register(
        email=data.email,
        password=data.password,
        full_name=data.full_name,
        org_name=data.org_name,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Login with email/password.
    Rate limited: 5 attempts/15min per IP.
    Account lockout: 10 failures → 1 hour lock.
    """
    service = AuthService(db)
    return await service.login(
        email=data.email,
        password=data.password,
        ip_address=_get_client_ip(request),
        device_info=data.device_info,
        user_agent=data.user_agent or request.headers.get("User-Agent"),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Rotate refresh token — old token invalidated, new pair issued.
    Prompt 3: "Refresh tokens rotativos"
    """
    service = AuthService(db)
    return await service.refresh(data.refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    data: RefreshRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Invalidate refresh token via Redis blacklist.
    Prompt 3: "POST /auth/logout → invalidar refresh token (Redis blacklist)"
    """
    service = AuthService(db)
    return await service.logout(data.refresh_token, user.id)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Send password reset email via Celery.
    Always returns success to prevent email enumeration.
    """
    service = AuthService(db)
    return await service.forgot_password(data.email)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Reset password using OTP token.
    Revokes all existing sessions.
    """
    service = AuthService(db)
    return await service.reset_password(
        token=data.token,
        new_password=data.new_password,
        ip_address=_get_client_ip(request),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Get current user profile with all org memberships.
    Prompt 3: "GET /auth/me → perfil + orgs + roles"
    """
    service = AuthService(db)
    return await service.get_me(user)


# ══════════════════════════════════════
# ORGANIZATION ENDPOINTS
# ══════════════════════════════════════

@router.post("/organizations", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    data: CreateOrganizationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    """Create a new organization."""
    service = AuthService(db)
    return await service.create_organization(data.name, user)


@router.get("/organizations/me", response_model=OrganizationDetailResponse)
async def get_my_organization(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> OrganizationDetailResponse:
    """
    Get current organization details with members.
    Requires X-Organization-ID header.
    """
    service = AuthService(db)
    return await service.get_my_organization(org.id, user)


@router.patch("/organizations/{org_id}", response_model=MessageResponse)
async def update_organization(
    org_id: uuid.UUID,
    data: UpdateOrganizationRequest,
    user: User = Depends(get_current_user),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Update organization details.
    Prompt 3: "PATCH /organizations/{id} → actualizar (solo ADMIN)"
    """
    if membership.role.value not in ("ORG_ADMIN", "SUPER_ADMIN"):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Admin role required", "code": "INSUFFICIENT_ROLE"},
        )

    service = AuthService(db)
    return await service.update_organization(
        org_id, user, name=data.name, logo_url=data.logo_url,
    )


@router.post("/organizations/invite", response_model=MessageResponse)
async def invite_member(
    data: InviteRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Invite a user by email to join the organization.
    Prompt 3: "POST /organizations/invite → invitar por email (Celery)"
    """
    if membership.role.value not in ("ORG_ADMIN", "SUPER_ADMIN"):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Admin role required", "code": "INSUFFICIENT_ROLE"},
        )

    service = AuthService(db)
    return await service.invite_member(org.id, data.email, data.role, user)


@router.post("/organizations/accept/{token}", response_model=MessageResponse)
async def accept_invitation(
    token: str,
    user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Accept an organization invitation.
    Prompt 3: "POST /organizations/accept/{token} → aceptar invitación"
    """
    service = AuthService(db)
    return await service.accept_invitation(token, user)


@router.get("/organizations/members", response_model=list[MemberResponse])
async def list_members(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    """List all members of the current organization."""
    service = AuthService(db)
    return await service.get_members(org.id)


@router.patch("/organizations/members/{member_id}", response_model=MessageResponse)
async def update_member_role(
    member_id: uuid.UUID,
    data: UpdateMemberRequest,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Change a member's role.
    Prompt 3: "PATCH /organizations/members/{id} → cambiar rol"
    """
    if membership.role.value not in ("ORG_ADMIN", "SUPER_ADMIN"):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Admin role required", "code": "INSUFFICIENT_ROLE"},
        )

    service = AuthService(db)
    return await service.update_member_role(org.id, member_id, data.role, user)


@router.delete("/organizations/members/{member_id}", response_model=MessageResponse)
async def remove_member(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    membership: OrganizationMember = Depends(get_org_membership),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Remove a member from the organization.
    Prompt 3: "DELETE /organizations/members/{id} → remover miembro"
    """
    if membership.role.value not in ("ORG_ADMIN", "SUPER_ADMIN"):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Admin role required", "code": "INSUFFICIENT_ROLE"},
        )

    service = AuthService(db)
    return await service.remove_member(org.id, member_id, user)
