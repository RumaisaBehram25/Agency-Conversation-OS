"""
Attora — Campaign Metrics & Breakdown Models

Per-entity (campaign/adset/ad) daily metrics from Meta Marketing API,
plus demographic and platform breakdown data.
"""

import uuid
from datetime import date

from sqlalchemy import (
    Date,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScopedMixin, TimestampMixin


class CampaignMetric(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "campaign_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # campaign|adset|ad

    # ── Meta Entity IDs ──────────────────────────────────────
    meta_campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_campaign_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_adset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_adset_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_ad_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_ad_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Campaign Config ──────────────────────────────────────
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ACTIVE, PAUSED, etc.
    objective: Mapped[str | None] = mapped_column(String(100), nullable=True)
    daily_budget: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # ── Core Metrics ─────────────────────────────────────────
    spend: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reach: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frequency: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    cpc: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    cpm: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    ctr: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    # ── Conversion Metrics ───────────────────────────────────
    leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_per_lead: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # ── Engagement Metrics ───────────────────────────────────
    link_clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    landing_page_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    video_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_engagement: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Messaging Metrics ────────────────────────────────────
    messaging_conversations_started: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    messaging_first_reply: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Relationships ────────────────────────────────────────
    organization = relationship("Organization", back_populates="campaign_metrics")

    __table_args__ = (
        UniqueConstraint(
            "org_id", "date", "level",
            "meta_campaign_id", "meta_adset_id", "meta_ad_id",
            name="uq_campaign_metrics_org_date_entity",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CampaignMetric(org_id={self.org_id}, date={self.date}, "
            f"level={self.level}, campaign={self.meta_campaign_id})>"
        )


class CampaignBreakdown(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "campaign_breakdowns"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # ── Meta Entity IDs ──────────────────────────────────────
    meta_campaign_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_adset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_ad_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Breakdown ────────────────────────────────────────────
    breakdown_type: Mapped[str] = mapped_column(String(50), nullable=False)  # age_gender|platform
    breakdown_key: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "25-34_male" or "instagram_feed"

    # ── Metrics ──────────────────────────────────────────────
    spend: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Relationships ────────────────────────────────────────
    organization = relationship("Organization", back_populates="campaign_breakdowns")

    __table_args__ = (
        UniqueConstraint(
            "org_id", "date",
            "meta_campaign_id", "meta_adset_id", "meta_ad_id",
            "breakdown_type", "breakdown_key",
            name="uq_campaign_breakdowns_org_date_entity_breakdown",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CampaignBreakdown(org_id={self.org_id}, date={self.date}, "
            f"type={self.breakdown_type}, key={self.breakdown_key})>"
        )
