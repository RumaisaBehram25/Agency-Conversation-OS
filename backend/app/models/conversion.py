"""
Attora — Conversion Event Model

Tracks conversion events (lead, purchase, etc.) with Meta CAPI
attribution data for ad performance tracking.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ConversionType, OrgScopedMixin, TimestampMixin


class ConversionEvent(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "conversion_events"

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
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversion_type: Mapped[ConversionType] = mapped_column(
        Enum(ConversionType, name="conversion_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)

    # ── Attribution ──────────────────────────────────────────
    ctwa_clid: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Meta CAPI ────────────────────────────────────────────
    capi_event_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capi_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capi_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Ad Context ───────────────────────────────────────────
    meta_ad_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Relationships ────────────────────────────────────────
    organization = relationship("Organization", back_populates="conversion_events")
    subscriber = relationship("Subscriber", back_populates="conversion_events")
    conversation = relationship("Conversation", back_populates="conversion_events")

    def __repr__(self) -> str:
        return f"<ConversionEvent(id={self.id}, type={self.conversion_type}, value={self.value})>"
