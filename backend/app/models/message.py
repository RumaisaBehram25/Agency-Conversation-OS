"""
Attora — Message Model

Stores individual messages in conversations, including AI metadata
(model used, response time, tokens, intent signals, compliance flags).
"""

import uuid

from sqlalchemy import (
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BuyerStage, MessageSender, TimestampMixin


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender: Mapped[MessageSender] = mapped_column(
        Enum(MessageSender, name="message_sender", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # ── AI Metadata ──────────────────────────────────────────
    intent_signals: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    buyer_stage_at_time: Mapped[BuyerStage | None] = mapped_column(
        Enum(BuyerStage, name="buyer_stage", values_callable=lambda x: [e.value for e in x], create_type=False),
        nullable=True,
    )
    compliance_flags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quick_replies: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # ── Relationships ────────────────────────────────────────
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, conversation_id={self.conversation_id}, sender={self.sender})>"
