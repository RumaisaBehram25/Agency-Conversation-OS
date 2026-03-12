"""
Attora — Daily Analytics Model

Pre-aggregated daily metrics per organization per channel.
Unique constraint on (org_id, date, channel) ensures one row per combo.
"""

import uuid
from datetime import date

from sqlalchemy import (
    Date,
    Enum,
    Integer,
    Numeric,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ChannelType, OrgScopedMixin, TimestampMixin


class DailyAnalytics(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "daily_analytics"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    channel: Mapped[ChannelType | None] = mapped_column(
        Enum(ChannelType, name="channel_type", values_callable=lambda x: [e.value for e in x], create_type=False),
        nullable=True,
    )

    # ── Conversation Metrics ─────────────────────────────────
    new_conversations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_conversations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_messages_per_conversation: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    avg_ai_response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Conversion Metrics ───────────────────────────────────
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversion_value: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    conversion_rate: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    # ── Cost Metrics ─────────────────────────────────────────
    ad_spend: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    cpa: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    roas: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    # ── AI Metrics ───────────────────────────────────────────
    ai_tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_cost: Mapped[float] = mapped_column(Numeric(10, 4), default=0, nullable=False)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Relationships ────────────────────────────────────────
    organization = relationship("Organization", back_populates="daily_analytics")

    __table_args__ = (
        UniqueConstraint("org_id", "date", "channel", name="uq_daily_analytics_org_date_channel"),
    )

    def __repr__(self) -> str:
        return f"<DailyAnalytics(org_id={self.org_id}, date={self.date}, channel={self.channel})>"
