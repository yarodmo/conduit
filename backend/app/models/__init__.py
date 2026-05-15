"""
Conduit Backend — Models Package
Re-export all models for Alembic discovery.
"""

from app.models.auth import (
    AuditLog,
    Invitation,
    PasswordResetToken,
    Organization,
    OrganizationMember,
    SubscriptionPlan,
    User,
    UserSession,
)
from app.models.base import AuditBase, ConduitBase
from app.models.field import FieldPhoto, WorkZone, ZoneProgressReport
from app.models.notifications import FCMToken, Notification, NotificationPreference
from app.models.assistant import AssistantCache, AssistantConversation, AssistantMessage
from app.models.learning import LearningCorrectionEvent, LearningInsight
from app.models.catalog import CatalogImportJob, CatalogSupplier
from app.models.collaboration import CollabSession, SessionParticipant
from app.models.reports import ReportJob
from app.models.plans import Plan, PlanPage, PlanProcessingJob
from app.models.projects import Project, ProjectMember
from app.models.rfis import ChangeOrder, Markup, RFI, RFIComment
from app.models.takeoff import MaterialCatalog, TakeoffItem, TakeoffJob

__all__ = [
    "ConduitBase",
    "AuditBase",
    "User",
    "Organization",
    "OrganizationMember",
    "UserSession",
    "Invitation",
    "PasswordResetToken",
    "SubscriptionPlan",
    "AuditLog",
    "Project",
    "ProjectMember",
    "Plan",
    "PlanPage",
    "PlanProcessingJob",
    "TakeoffJob",
    "TakeoffItem",
    "MaterialCatalog",
    "Markup",
    "RFI",
    "RFIComment",
    "ChangeOrder",
    "WorkZone",
    "ZoneProgressReport",
    "FieldPhoto",
    "Notification",
    "NotificationPreference",
    "FCMToken",
    "ReportJob",
    "CollabSession",
    "SessionParticipant",
    "CatalogSupplier",
    "CatalogImportJob",
    "AssistantConversation",
    "AssistantMessage",
    "AssistantCache",
    "LearningInsight",
    "LearningCorrectionEvent",
]
