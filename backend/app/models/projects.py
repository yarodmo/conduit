"""
Conduit Backend — Project Models
Prompt 2 Entities: 3. PROYECTOS
Prompt 4: Project Management — Multi-Scale

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ConduitBase


# ══════════════════════════════════════
# ENUMS
# ══════════════════════════════════════

class ProjectType(str, enum.Enum):
    """Prompt 2: project types with multi-scale support."""
    RESIDENTIAL_SINGLE = "residential_single"
    RESIDENTIAL_MULTI = "residential_multi"
    SMALL_COMMERCIAL = "small_commercial"
    COMMERCIAL = "commercial"
    INSTITUTIONAL = "institutional"
    INDUSTRIAL = "industrial"


class ProjectComplexity(str, enum.Enum):
    """Auto-detected complexity level."""
    SIMPLE = "simple"
    STANDARD = "standard"
    COMPLEX = "complex"


class ProjectMemberRole(str, enum.Enum):
    """
    Prompt 2: "project_members: user + project + role"
    PROJECT_MANAGER, ENGINEER, FIELD_SUPERVISOR, FIELD_TECH, VIEWER, OWNER
    """
    PROJECT_MANAGER = "PROJECT_MANAGER"
    ENGINEER = "ENGINEER"
    FIELD_SUPERVISOR = "FIELD_SUPERVISOR"
    FIELD_TECH = "FIELD_TECH"
    VIEWER = "VIEWER"
    OWNER = "OWNER"


# ══════════════════════════════════════
# PROJECT
# ══════════════════════════════════════

class Project(ConduitBase):
    """
    Prompt 2: "projects — type, complexity, address, general_contractor, owner_name"
    Prompt 4: Multi-scale onboarding (3-step simple, 5-step complex).
    """
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[ProjectType] = mapped_column(
        Enum(ProjectType, name="project_type_enum", create_constraint=True),
        nullable=False,
        default=ProjectType.RESIDENTIAL_SINGLE,
    )
    complexity: Mapped[ProjectComplexity] = mapped_column(
        Enum(ProjectComplexity, name="project_complexity_enum", create_constraint=True),
        nullable=False,
        default=ProjectComplexity.SIMPLE,
    )
    address: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
    )
    city: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    state: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )
    zip_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
    )
    general_contractor: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )
    owner_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    metadata_extra: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None,
    )

    # Relationships
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", lazy="selectin",
    )

    __table_args__ = (
        Index("ix_projects_org_id", "org_id"),
        Index("ix_projects_type", "type"),
    )


# ══════════════════════════════════════
# PROJECT MEMBER
# ══════════════════════════════════════

class ProjectMember(ConduitBase):
    """
    Prompt 2: "project_members: user + project + role"
    """
    __tablename__ = "project_members"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ProjectMemberRole] = mapped_column(
        Enum(ProjectMemberRole, name="project_member_role_enum", create_constraint=True),
        nullable=False,
        default=ProjectMemberRole.VIEWER,
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="members")

    __table_args__ = (
        Index("ix_project_members_user_project", "user_id", "project_id", unique=True),
        Index("ix_project_members_project_id", "project_id"),
    )
