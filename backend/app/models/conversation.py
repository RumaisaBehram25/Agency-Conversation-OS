"""
Attora — Conversation Model

Tracks individual conversations between subscribers and the AI,
including status, message counts, and response time metrics.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    ChannelType,
    ConversationStatus,
    OrgScopedMixin,
    TimestampMixin,
)


class Conversation(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("subscribers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, name="channel_type", values_callable=lambda x: [e.value for e in x], create_type=False),
        nullable=False,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status", values_callable=lambda x: [e.value for e in x]),
        default=ConversationStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_response_time_avg_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Timestamps ───────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ────────────────────────────────────────
    organization = relationship("Organization", back_populates="conversations")
    subscriber = relationship("Subscriber", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    conversion_events = relationship("ConversionEvent", back_populates="conversation")

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, subscriber_id={self.subscriber_id}, status={self.status})>"
