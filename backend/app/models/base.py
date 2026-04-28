"""
Conduit Backend — SQLAlchemy 2.0 Base Models
Prompt 2 Compliance: UUID PKs, timestamps, soft-delete, audit trail.
LAW 29: Decimal precision for all engineering calculations.

Bliss Systems LLC — APEX Standard
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ConduitBase(DeclarativeBase):
    """
    Base class for ALL Conduit models.

    Enforces:
    - UUID primary keys (Prompt 2: "UUID para todas las PKs")
    - created_at / updated_at timestamps
    - soft-delete via deleted_at
    """

    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
        dict[str, Any]: None,  # Override per-field with JSONB
    }

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if record is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark record as soft-deleted."""
        self.deleted_at = datetime.now().astimezone()


class AuditBase(DeclarativeBase):
    """
    Base class for APPEND-ONLY audit tables.

    Prompt 2: "audit_logs: APPEND-ONLY, sin updated_at ni deleted_at"

    These records are IMMUTABLE once written.
    Legal evidence trail for construction contracts.
    """

    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # NO updated_at — IMMUTABLE
    # NO deleted_at — NEVER deleted
