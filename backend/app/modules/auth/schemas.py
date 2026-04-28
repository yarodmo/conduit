"""
Conduit Backend — Auth Module Pydantic V2 Schemas
Prompt 3: All request/response schemas for Auth & Organizations.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ══════════════════════════════════════
# AUTH — Request Schemas
# ══════════════════════════════════════

class RegisterRequest(BaseModel):
    """
    Registration creates user + org in atomic transaction.
    Prompt 3: "POST /auth/register → user + org en transacción atómica"
    """
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=255)
    org_name: str = Field(..., min_length=2, max_length=255)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        """Enforce password complexity."""
        if not any(c.isupper() for c in v):
            msg = "Password must contain at least one uppercase letter"
            raise ValueError(msg)
        if not any(c.islower() for c in v):
            msg = "Password must contain at least one lowercase letter"
            raise ValueError(msg)
        if not any(c.isdigit() for c in v):
            msg = "Password must contain at least one digit"
            raise ValueError(msg)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_info: str | None = None
    user_agent: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            msg = "Password must contain at least one uppercase letter"
            raise ValueError(msg)
        if not any(c.islower() for c in v):
            msg = "Password must contain at least one lowercase letter"
            raise ValueError(msg)
        if not any(c.isdigit() for c in v):
            msg = "Password must contain at least one digit"
            raise ValueError(msg)
        return v


# ══════════════════════════════════════
# AUTH — Response Schemas
# ══════════════════════════════════════

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds

    model_config = ConfigDict(from_attributes=True)


class OrgMembershipResponse(BaseModel):
    org_id: uuid.UUID
    org_name: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    avatar_url: str | None = None
    is_active: bool
    created_at: datetime
    organizations: list[OrgMembershipResponse] = []

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Generic success message response."""
    message: str
    details: dict | None = None


# ══════════════════════════════════════
# ORGANIZATION — Request/Response
# ══════════════════════════════════════

class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    logo_url: str | None = None


class InviteRequest(BaseModel):
    """Prompt 3: "POST /organizations/invite → invitar por email"."""
    email: EmailStr
    role: str = Field(default="ORG_MEMBER")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"SUPER_ADMIN", "ORG_ADMIN", "ORG_MEMBER"}
        if v not in allowed:
            msg = f"Role must be one of: {', '.join(allowed)}"
            raise ValueError(msg)
        return v


class MemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateMemberRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"SUPER_ADMIN", "ORG_ADMIN", "ORG_MEMBER"}
        if v not in allowed:
            msg = f"Role must be one of: {', '.join(allowed)}"
            raise ValueError(msg)
        return v


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None = None
    member_count: int = 0
    plan_name: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationDetailResponse(OrganizationResponse):
    members: list[MemberResponse] = []
    preferred_suppliers: dict | None = None
