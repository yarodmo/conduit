"""
Conduit Backend — FastAPI Dependencies
Prompt 3 RBAC:
  @require_org_role("ORG_ADMIN") → decorator for org-level
  @require_project_role("ENGINEER") → decorator for project-level
  @require_permission("takeoff:execute") → granular permission check
  Middleware X-Organization-ID → tenant isolation

Bliss Systems LLC — APEX Standard
"""

import uuid
from functools import wraps
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import Permission, Role, has_permission
from app.core.redis import is_token_blacklisted
from app.core.security import verify_access_token
from app.models.auth import Organization, OrganizationMember, User

# ── Bearer Token Extraction ──
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate JWT, return authenticated User.

    Checks:
    1. Token present and valid
    2. Token not blacklisted (revoked)
    3. User exists and is active
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required", "code": "AUTH_REQUIRED"},
        )

    try:
        payload = verify_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid or expired token", "code": "INVALID_TOKEN"},
        )

    # Check blacklist
    jti = payload.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token has been revoked", "code": "TOKEN_REVOKED"},
        )

    # Load user
    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found or inactive", "code": "USER_INACTIVE"},
        )

    return user


async def get_current_org(
    request: Request,
    x_organization_id: str | None = Header(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """
    Extract X-Organization-ID header and validate membership.
    Prompt 3: "Middleware X-Organization-ID → tenant isolation en todo request"
    """
    if not x_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "X-Organization-ID header required",
                "code": "ORG_ID_MISSING",
            },
        )

    try:
        org_id = uuid.UUID(x_organization_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid organization ID format", "code": "INVALID_ORG_ID"},
        )

    # Verify org exists
    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Organization not found", "code": "ORG_NOT_FOUND"},
        )

    # Verify user is member of this org — TENANT ISOLATION
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.org_id == org_id,
            OrganizationMember.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()

    if not membership and not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "You are not a member of this organization",
                "code": "NOT_ORG_MEMBER",
            },
        )

    # Store in request state for downstream use
    request.state.org_id = org_id
    request.state.org = org
    request.state.membership = membership

    return org


async def get_org_membership(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> OrganizationMember:
    """Get the current user's membership in the current org."""
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.org_id == org.id,
            OrganizationMember.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Not a member of this organization", "code": "NOT_ORG_MEMBER"},
        )

    return membership


def require_org_role(*required_roles: str):
    """
    Decorator factory: require org-level role.

    Usage:
        @router.post("/")
        @require_org_role("ORG_ADMIN")
        async def create_something(...):
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            membership: OrganizationMember | None = kwargs.get("membership")
            user: User | None = kwargs.get("user")

            if user and user.is_superadmin:
                return await func(*args, **kwargs)

            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Organization membership required", "code": "NO_MEMBERSHIP"},
                )

            if membership.role.value not in required_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": f"Required role: {', '.join(required_roles)}",
                        "code": "INSUFFICIENT_ROLE",
                    },
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_permission(permission: str):
    """
    Decorator factory: check granular permission from RBAC matrix.

    Usage:
        @router.post("/takeoff/{id}/run")
        @require_permission("takeoff:run")
        async def run_takeoff(...):
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            membership: OrganizationMember | None = kwargs.get("membership")
            user: User | None = kwargs.get("user")

            if user and user.is_superadmin:
                return await func(*args, **kwargs)

            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Membership required", "code": "NO_MEMBERSHIP"},
                )

            # Map org role to permissions.py Role enum
            try:
                role_enum = Role(membership.role.value)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "Unknown role", "code": "UNKNOWN_ROLE"},
                )

            try:
                perm_enum = Permission(permission)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"error": "Unknown permission", "code": "UNKNOWN_PERMISSION"},
                )

            if not has_permission(role_enum, perm_enum):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": f"Permission denied: {permission}",
                        "code": "PERMISSION_DENIED",
                    },
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
