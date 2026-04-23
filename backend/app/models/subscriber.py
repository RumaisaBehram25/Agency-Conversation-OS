"""
Attora — Subscriber Model

Mirror of ManyChat subscribers, enriched with AI-derived buyer stage,
interests, objections, and conversion data. Scoped to organization.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BuyerStage, ChannelType, OrgScopedMixin, TimestampMixin


class Subscriber(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "subscribers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    manychat_subscriber_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, name="channel_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # ── Identity ─────────────────────────────────────────────
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Attribution ──────────────────────────────────────────
    ctwa_clid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    ad_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ad_set_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Attora Campaign Link (compliance) ────────────────────
    # Set only when the subscriber's meta campaign_id matches a registered
    # AdCampaign for this org. A NULL value means the lead arrived via a
    # campaign that is NOT flagged as Attora-managed → do not reach out.
    attora_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ad_campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # First-touch UTM params from intake (e.g. ManyChat custom fields)
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── AI Context ───────────────────────────────────────────
    buyer_stage: Mapped[BuyerStage] = mapped_column(
        Enum(BuyerStage, name="buyer_stage", values_callable=lambda x: [e.value for e in x]),
        default=BuyerStage.AWARENESS,
        nullable=False,
        index=True,
    )
    interests: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    objections_raised: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    conversation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Conversion Status ────────────────────────────────────
    is_converted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    conversion_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hyros_purchased: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hyros_product: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hyros_purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hyros_lead_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    hyros_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hyros_origin_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hyros_origin_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hyros_traffic_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hyros_creative_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hyros_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Activity Metadata ────────────────────────────────────
    first_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Relationships ────────────────────────────────────────
    organization = relationship("Organization", back_populates="subscribers")
    conversations = relationship("Conversation", back_populates="subscriber", cascade="all, delete-orphan")
    conversion_events = relationship("ConversionEvent", back_populates="subscriber", cascade="all, delete-orphan")
    attora_campaign = relationship("AdCampaign", back_populates="subscribers")

    __table_args__ = (
        UniqueConstraint("org_id", "manychat_subscriber_id", name="uq_subscribers_org_manychat"),
    )

    def __repr__(self) -> str:
        return f"<Subscriber(id={self.id}, manychat_id={self.manychat_subscriber_id!r}, stage={self.buyer_stage})>"
