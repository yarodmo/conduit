"""
Conduit Backend — Security Monitor Models (M14)
Runtime threat detection + event audit trail.

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ConduitBase


class SecurityEventType(str, enum.Enum):
    SQLI_ATTEMPT       = "sqli_attempt"
    PATH_TRAVERSAL     = "path_traversal"
    BRUTE_FORCE        = "brute_force"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_PAYLOAD = "suspicious_payload"
    TENANT_VIOLATION   = "tenant_violation"
    INVALID_TOKEN      = "invalid_token"
    SCANNER_DETECTED   = "scanner_detected"
    ANOMALOUS_REQUEST  = "anomalous_request"
    TEST_EVENT         = "test_event"


class SecuritySeverity(str, enum.Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


# Severity by event type — guides auto-escalation
SEVERITY_MAP: dict[SecurityEventType, SecuritySeverity] = {
    SecurityEventType.SQLI_ATTEMPT:        SecuritySeverity.CRITICAL,
    SecurityEventType.PATH_TRAVERSAL:      SecuritySeverity.HIGH,
    SecurityEventType.BRUTE_FORCE:         SecuritySeverity.HIGH,
    SecurityEventType.TENANT_VIOLATION:    SecuritySeverity.CRITICAL,
    SecurityEventType.SCANNER_DETECTED:    SecuritySeverity.HIGH,
    SecurityEventType.RATE_LIMIT_EXCEEDED: SecuritySeverity.MEDIUM,
    SecurityEventType.SUSPICIOUS_PAYLOAD:  SecuritySeverity.HIGH,
    SecurityEventType.INVALID_TOKEN:       SecuritySeverity.LOW,
    SecurityEventType.ANOMALOUS_REQUEST:   SecuritySeverity.LOW,
    SecurityEventType.TEST_EVENT:          SecuritySeverity.LOW,
}


class SecurityEvent(ConduitBase):
    __tablename__ = "security_events"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
