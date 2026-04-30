"""
Attora — Ad Campaign & UTM Models

AdCampaign: tracks ad campaigns that Attora manages, linking Meta campaign IDs
to Attora-specific tracking. Prerequisite story: is_attora_managed flag.

CampaignUTM: stores generated UTM parameter sets for each campaign's funnel pages
(product page, checkout, purchase success). One UTM set per campaign.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScopedMixin, TimestampMixin


class AdCampaign(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "ad_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Meta attribution — links to existing subscriber.campaign_id / ad_id fields
    meta_campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    meta_ad_set_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 'paid'  → Meta paid campaign (meta_campaign_id is the join key)
    # 'organic' → no Meta entity; routed by `keyword` from ManyChat trigger
    source_type: Mapped[str] = mapped_column(String(20), default="paid", nullable=False, index=True)

    # Comment-trigger keyword that routes leads to this campaign on subscriber
    # upsert. Required for source_type='organic'; optional for 'paid'.
    # Uniqueness enforced per-org via partial unique index (see __table_args__).
    keyword: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Prerequisite story: flag specifying this campaign is Attora-managed
    is_attora_managed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Optional link to product this campaign promotes
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="ad_campaigns")
    product = relationship("Product")
    utm = relationship(
        "CampaignUTM",
        back_populates="campaign",
        uselist=False,
        cascade="all, delete-orphan",
    )
    subscribers = relationship("Subscriber", back_populates="attora_campaign")

    __table_args__ = (
        # Per-org keyword uniqueness — only enforced when keyword is set, so
        # paid campaigns without a keyword don't collide on NULL.
        Index(
            "uq_ad_campaigns_org_keyword",
            "org_id",
            "keyword",
            unique=True,
            postgresql_where=sa.text("keyword IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<AdCampaign(id={self.id}, name={self.name!r}, source={self.source_type}, attora={self.is_attora_managed})>"


class CampaignUTM(Base, TimestampMixin, OrgScopedMixin):
    """
    UTM parameter set for an ad campaign's conversion funnel.

    Stores base URLs for each stage plus the generated full URLs with UTM params
    so customers can copy and apply them immediately.
    """

    __tablename__ = "campaign_utms"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ad_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # UTM source parameters
    utm_source: Mapped[str] = mapped_column(String(100), default="attora", nullable=False)
    utm_medium: Mapped[str] = mapped_column(String(100), default="messaging", nullable=False)
    utm_campaign: Mapped[str] = mapped_column(String(255), nullable=False)

    # Base URLs provided by the customer
    product_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full generated URLs with UTM params appended
    product_page_utm_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkout_utm_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_utm_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    campaign = relationship("AdCampaign", back_populates="utm")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("org_id", "campaign_id", name="uq_campaign_utms_org_campaign"),
    )

    def __repr__(self) -> str:
        return f"<CampaignUTM(campaign_id={self.campaign_id}, utm_campaign={self.utm_campaign!r})>"
