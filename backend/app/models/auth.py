"""
Conduit Backend — Auth & Organization Models
Prompt 2 Entities: 1. MULTI-TENANCY + 2. AUTH
Prompt 3: Auth & Organizations module specification.

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AuditBase, ConduitBase


# ══════════════════════════════════════
# ENUMS — Single Source of Truth
# ══════════════════════════════════════

class OrgRole(str, enum.Enum):
    """Organization-level roles. Prompt 3 RBAC."""
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    ORG_MEMBER = "ORG_MEMBER"


class ProjectRole(str, enum.Enum):
    """Project-level roles. Prompt 3 RBAC."""
    PROJECT_MANAGER = "PROJECT_MANAGER"
    ENGINEER = "ENGINEER"
    FIELD_SUPERVISOR = "FIELD_SUPERVISOR"
    FIELD_TECH = "FIELD_TECH"
    VIEWER = "VIEWER"
    OWNER = "OWNER"
    PE_REVIEWER = "PE_REVIEWER"  # ADR-004: M15


class AuditAction(str, enum.Enum):
    """Audit trail action types."""
    USER_REGISTERED = "user.registered"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_PASSWORD_RESET = "user.password_reset"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USER_LOCKED = "user.locked"
    USER_UNLOCKED = "user.unlocked"
    ORG_CREATED = "org.created"
    ORG_UPDATED = "org.updated"
    ORG_MEMBER_INVITED = "org.member.invited"
    ORG_MEMBER_JOINED = "org.member.joined"
    ORG_MEMBER_ROLE_CHANGED = "org.member.role_changed"
    ORG_MEMBER_REMOVED = "org.member.removed"
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_DELETED = "project.deleted"


# ══════════════════════════════════════
# USER — Global, multi-org
# ══════════════════════════════════════

class User(ConduitBase):
    """
    Global user account. Can belong to multiple organizations.
    Prompt 2: "users: global, múltiples orgs"
    """
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    is_superadmin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    org_memberships: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="user", lazy="selectin",
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", lazy="noload",
    )


# ══════════════════════════════════════
# ORGANIZATION — Multi-tenancy root
# ══════════════════════════════════════

class Organization(ConduitBase):
    """
    Organization / tenant root.
    Prompt 2: "organizations — name, logo_url, plan_id, ..."
    """
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    logo_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscription_plans.id"),
        nullable=True,
    )
    annual_construction_volume_usd: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )
    preferred_suppliers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None,
    )
    learned_materials: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None,
    )

    # Relationships
    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", lazy="selectin",
    )
    plan: Mapped["SubscriptionPlan | None"] = relationship(
        lazy="joined",
    )


# ══════════════════════════════════════
# ORGANIZATION MEMBER — user + org + role
# ══════════════════════════════════════

class OrganizationMember(ConduitBase):
    """
    Prompt 2: "organization_members: user + org + role"
    Junction table with role assignment.
    """
    __tablename__ = "organization_members"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, name="org_role_enum", create_constraint=True),
        nullable=False,
        default=OrgRole.ORG_MEMBER,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="org_memberships")
    organization: Mapped["Organization"] = relationship(back_populates="members")

    __table_args__ = (
        Index("ix_org_members_user_org", "user_id", "org_id", unique=True),
        Index("ix_org_members_org_id", "org_id"),
    )


# ══════════════════════════════════════
# USER SESSION — JWT refresh tokens
# ══════════════════════════════════════

class UserSession(ConduitBase):
    """
    Prompt 2: "user_sessions: JWT refresh tokens + device_info + last_ip"
    Prompt 3: "Refresh tokens rotativos — cada uso genera nuevo token"
    """
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True,
    )
    device_info: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
    )
    last_ip: Mapped[str | None] = mapped_column(
        String(45), nullable=True,  # IPv6 max length
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="sessions")


# ══════════════════════════════════════
# INVITATION — Email invite flow
# ══════════════════════════════════════

class Invitation(ConduitBase):
    """
    Prompt 2: "invitations: email + token + org + role + expires_at"
    Prompt 3: Register → invite flow in < 5 clicks.
    """
    __tablename__ = "invitations"

    email: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    token: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, name="org_role_enum", create_constraint=True, create_type=False),
        nullable=False,
        default=OrgRole.ORG_MEMBER,
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


# ══════════════════════════════════════
# PASSWORD RESET TOKEN — GAP-001 FIX
# Dedicated table, no UUID-zero hack
# ══════════════════════════════════════

class PasswordResetToken(ConduitBase):
    """
    Dedicated password reset token — separate from Invitation.

    GAP-001 Fix: Previously, forgot_password() reused invitations table
    with org_id=UUID(int=0), violating FK constraint in production.
    This table has no org_id FK — resets are user-scoped, not org-scoped.
    """
    __tablename__ = "password_reset_tokens"

    email: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    token: Mapped[str] = mapped_column(
        String(512), unique=True, nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True,
    )

    __table_args__ = (
        Index("ix_password_reset_token_tok", "token"),
        Index("ix_password_reset_token_user", "user_id"),
    )


# ══════════════════════════════════════
# SUBSCRIPTION PLAN — Tier limits
# ══════════════════════════════════════

class SubscriptionPlan(ConduitBase):
    """
    Prompt 2: "subscription_plans: free, starter, pro, enterprise"
    """
    __tablename__ = "subscription_plans"

    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    price_monthly_usd: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,  # Cents
    )
    price_annual_usd: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,  # Cents
    )
    limits: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False,
        default={
            "max_projects": 3,
            "max_pages": 50,
            "max_ai_takeoffs_per_month": 5,
            "max_users": 5,
        },
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )


# ══════════════════════════════════════
# AUDIT LOG — APPEND-ONLY (AuditBase)
# ══════════════════════════════════════

class AuditLog(AuditBase):
    """
    Prompt 2: "audit_logs: APPEND-ONLY"
    "entity_type, entity_id, action, user_id, org_id"
    "before_state: JSONB, after_state: JSONB"
    "ip_address, user_agent, timestamp"
    "NOTA: Esta tabla es el audit trail legal requerido en contratos de construcción."

    IMMUTABLE — no updated_at, no deleted_at, no UPDATE/DELETE operations.
    """
    __tablename__ = "audit_logs"

    entity_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    before_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True,
    )
    after_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_org", "org_id"),
        Index("ix_audit_logs_user", "user_id"),
        Index("ix_audit_logs_created", "created_at"),
    )
