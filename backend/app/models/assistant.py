"""
Conduit Backend — AI Assistant Models (M10)
Conversation threading + offline response cache.

Bliss Systems LLC — APEX Standard
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ConduitBase


class ContextType(str, enum.Enum):
    TAKEOFF_QUESTION = "takeoff_question"
    PLAN_QUESTION    = "plan_question"
    RFI_HELP         = "rfi_help"
    FIELD_QUESTION   = "field_question"
    GENERAL          = "general"
    HOW_TO           = "how_to"


class AssistantConversation(ConduitBase):
    __tablename__ = "assistant_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    context_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    messages: Mapped[list["AssistantMessage"]] = relationship(
        "AssistantMessage", back_populates="conversation",
        cascade="all, delete-orphan", order_by="AssistantMessage.created_at",
    )


class AssistantMessage(ConduitBase):
    __tablename__ = "assistant_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    conversation: Mapped["AssistantConversation"] = relationship(
        "AssistantConversation", back_populates="messages",
    )


class AssistantCache(ConduitBase):
    __tablename__ = "assistant_cache"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_type: Mapped[str] = mapped_column(String(30), nullable=False)
    question: Mapped[str] = mapped_column(Text(), nullable=False)
    response: Mapped[str] = mapped_column(Text(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
