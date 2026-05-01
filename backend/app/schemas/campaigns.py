"""
Attora — Campaign Drill-Down Pydantic Schemas

Response models for campaign list, detail, ad set, ad, and breakdown endpoints.
"""

from datetime import date

from pydantic import BaseModel


class CampaignSummary(BaseModel):
    """Aggregated campaign summary for the campaigns list."""

    meta_campaign_id: str
    meta_campaign_name: str | None = None
    status: str | None = None
    source_type: str = "paid"
    daily_budget: float | None = None
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
    link_clicks: int = 0
    video_views: int = 0
    post_engagement: int = 0
    cpc: float | None = None
    cpm: float | None = None
    ctr: float | None = None


class CampaignDailyMetric(BaseModel):
    """Single day of metrics for a campaign detail time series."""

    date: date
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
    cpc: float | None = None
    cpm: float | None = None
    ctr: float | None = None
    reach: int = 0
    frequency: float | None = None


class AdSetSummary(BaseModel):
    """Aggregated ad set summary within a campaign."""

    meta_adset_id: str
    meta_adset_name: str | None = None
    status: str | None = None
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
    link_clicks: int = 0
    video_views: int = 0
    cpc: float | None = None
    cpm: float | None = None
    ctr: float | None = None


class AdSummary(BaseModel):
    """Aggregated ad summary within an ad set."""

    meta_ad_id: str
    meta_ad_name: str | None = None
    status: str | None = None
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
    link_clicks: int = 0
    video_views: int = 0
    cpc: float | None = None
    cpm: float | None = None
    ctr: float | None = None


class BreakdownItem(BaseModel):
    """Single breakdown row (age_gender or platform)."""

    breakdown_key: str
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    leads: int = 0
