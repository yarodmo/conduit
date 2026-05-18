"""
Conduit Backend — Projects Schemas (Pydantic v2)
Sprint 2: Request / Response models for Projects + Team Membership

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════
# REQUEST SCHEMAS
# ══════════════════════════════════════

class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(None, max_length=2000)
    type: str = Field(..., description="ProjectType enum value")
    complexity: str = Field(
        default="simple",
        description="ProjectComplexity: simple | standard | complex",
    )
    address: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=50)
    zip_code: str | None = Field(None, max_length=20)
    general_contractor: str | None = Field(None, max_length=255)
    owner_name: str | None = Field(None, max_length=255)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {
            "residential_single", "residential_multi", "small_commercial",
            "commercial", "institutional", "industrial",
        }
        if v not in valid:
            raise ValueError(f"Invalid project type. Must be one of: {sorted(valid)}")
        return v

    @field_validator("complexity")
    @classmethod
    def validate_complexity(cls, v: str) -> str:
        valid = {"simple", "standard", "complex"}
        if v not in valid:
            raise ValueError(f"Invalid complexity. Must be one of: {sorted(valid)}")
        return v


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = Field(None, max_length=2000)
    address: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=50)
    zip_code: str | None = Field(None, max_length=20)
    general_contractor: str | None = Field(None, max_length=255)
    owner_name: str | None = Field(None, max_length=255)
    complexity: str | None = Field(None)
    is_active: bool | None = None

    @field_validator("complexity")
    @classmethod
    def validate_complexity(cls, v: str | None) -> str | None:
        if v is not None and v not in {"simple", "standard", "complex"}:
            raise ValueError("Invalid complexity value")
        return v


class ProjectMemberAddRequest(BaseModel):
    user_id: uuid.UUID
    role: str = Field(..., description="ProjectMemberRole value")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid = {"PROJECT_MANAGER", "ENGINEER", "FIELD_SUPERVISOR", "FIELD_TECH", "VIEWER"}
        if v not in valid:
            raise ValueError(f"Invalid role. OWNER cannot be assigned. Valid: {sorted(valid)}")
        return v


class ProjectMemberUpdateRoleRequest(BaseModel):
    role: str = Field(..., description="ProjectMemberRole value (not OWNER)")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid = {"PROJECT_MANAGER", "ENGINEER", "FIELD_SUPERVISOR", "FIELD_TECH", "VIEWER"}
        if v not in valid:
            raise ValueError(f"Invalid role. OWNER cannot be re-assigned. Valid: {sorted(valid)}")
        return v


# ══════════════════════════════════════
# RESPONSE SCHEMAS
# ══════════════════════════════════════

class ProjectMemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None
    type: str
    complexity: str
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    general_contractor: str | None
    owner_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectDetailResponse(ProjectResponse):
    """Extended response including team members — single JOIN query."""
    members: list[ProjectMemberResponse] = []


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int


# ══════════════════════════════════════
# ONBOARDING SCHEMAS (Sprint 6 / T2)
# ══════════════════════════════════════

class OnboardingStep(BaseModel):
    key: str
    label: str
    completed: bool
    required: bool = True


class OnboardingStatusResponse(BaseModel):
    """
    Tells the frontend which wizard mode to render.

    mode="simplified"  → 3-step wizard (residential_single, small_commercial,
                         or complexity=simple) — designed for field techs and
                         small residential contractors.
    mode="standard"    → 5-step wizard (commercial, institutional, industrial).

    The frontend uses `steps` to render the progress bar and `next_step_key`
    to know which panel to open.
    """
    project_id: uuid.UUID
    mode: str
    steps_total: int
    steps_completed: int
    next_step_key: str | None
    is_complete: bool
    steps: list[OnboardingStep]
