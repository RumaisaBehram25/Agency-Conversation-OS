"""
Request / response for POST /api/settings/meta/integration-test.

Lets admins paste Meta fields in Swagger, optionally persist them, and see
whether Marketing API returns account info, spend, and campaigns.
"""

from typing import Any

from pydantic import BaseModel, Field


class MetaIntegrationTestRequest(BaseModel):
    """Optional Meta fields. Omitted values keep the organization's stored settings."""

    meta_pixel_id: str | None = None
    meta_capi_token: str | None = Field(
        None,
        description="Plaintext token. If persist=true, encrypted and saved like PUT /settings.",
    )
    meta_ad_account_id: str | None = Field(
        None,
        description="Numeric or act_ prefixed ad account id.",
    )
    meta_page_id: str | None = None
    meta_business_manager_id: str | None = None
    persist: bool = Field(
        True,
        description="If true, every non-null field above is written to the org before the sample fetch.",
    )
    spend_days: int = Field(
        7,
        ge=1,
        le=30,
        description="Number of days ending yesterday for the daily spend sample.",
    )
    campaigns_limit: int = Field(
        25,
        ge=1,
        le=100,
        description="Max campaigns returned in the sample list.",
    )


class MetaIntegrationTestResponse(BaseModel):
    persisted: bool
    persisted_field_names: list[str] = Field(default_factory=list)
    effective_meta_ad_account_id: str | None = None
    effective_meta_pixel_id: str | None = None
    access_token_configured: bool = False
    ad_account: dict[str, Any] | None = None
    ad_account_error: str | None = None
    daily_spend: list[dict[str, Any]] = Field(default_factory=list)
    campaigns: list[dict[str, Any]] = Field(default_factory=list)
    ok: bool = False
    message: str = ""


class MetaSyncNowRequest(BaseModel):
    """Payload for POST /api/settings/meta/sync-now."""

    days_back: int = Field(
        7,
        ge=1,
        le=90,
        description="Number of days to sync ending yesterday.",
    )
    granular: bool = Field(
        True,
        description=(
            "If true, also sync campaign/adset/ad metrics + demographic and "
            "platform breakdowns (slower but needed for drilldowns)."
        ),
    )
    source_type: str | None = Field(
        None,
        description="Limit granular sync to campaigns of this source type: 'paid' or 'organic'. Omit to sync all.",
    )


class MetaSyncNowResponse(BaseModel):
    started: bool
    days_back: int
    granular: bool
    message: str
    # Populated when the sync completes synchronously. None on early-exit errors.
    campaigns_imported: int | None = None
    campaigns_synced: int | None = None
    adsets_synced: int | None = None
    ads_synced: int | None = None
    dates_updated: int | None = None
    total_spend: float | None = None
    errors: list[str] | None = None
