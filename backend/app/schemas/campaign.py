"""
Attora — Campaign & UTM Schemas

Pydantic models for ad campaign creation, updates, and UTM generation.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from pydantic import BaseModel, Field, field_validator, model_validator


# ── UTM Helpers ──────────────────────────────────────────────


def _slugify(text: str) -> str:
    """Convert campaign name to a URL-safe slug for utm_campaign parameter."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "campaign"


def build_utm_url(base_url: str, utm_params: dict[str, str]) -> str:
    """Append UTM parameters to a URL, preserving any existing query params."""
    parsed = urlparse(base_url)
    existing = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    merged = {**existing, **utm_params}
    new_query = urlencode(merged)
    return urlunparse(parsed._replace(query=new_query))


def generate_utm_urls(
    utm_source: str,
    utm_medium: str,
    utm_campaign: str,
    product_page_url: str | None,
    checkout_url: str | None,
    success_url: str | None,
) -> tuple[str | None, str | None, str | None]:
    """
    Build the three funnel-stage UTM URLs.

    Returns (product_page_utm_url, checkout_utm_url, success_utm_url).
    """
    base_params = {
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
    }

    def _make(url: str | None, content: str) -> str | None:
        if not url:
            return None
        return build_utm_url(url, {**base_params, "utm_content": content})

    return (
        _make(product_page_url, "product_page"),
        _make(checkout_url, "checkout"),
        _make(success_url, "success"),
    )


# ── Ad Campaign Schemas ──────────────────────────────────────


class AdCampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    meta_campaign_id: str | None = None
    meta_ad_set_id: str | None = None
    is_attora_managed: bool = True
    product_id: uuid.UUID | None = None
    is_active: bool = True


class AdCampaignUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    meta_campaign_id: str | None = None
    meta_ad_set_id: str | None = None
    is_attora_managed: bool | None = None
    product_id: uuid.UUID | None = None
    is_active: bool | None = None


# ── UTM Schemas ──────────────────────────────────────────────


class UTMGenerateRequest(BaseModel):
    """Request to generate (or regenerate) UTM URLs for a campaign."""

    product_page_url: str | None = Field(
        None, description="Base URL of the product landing page"
    )
    checkout_url: str | None = Field(
        None, description="Base URL of the checkout page"
    )
    success_url: str | None = Field(
        None, description="Base URL of the purchase success / thank-you page"
    )
    utm_source: str = Field("attora", max_length=100)
    utm_medium: str = Field("messaging", max_length=100)
    utm_campaign: str | None = Field(
        None,
        max_length=255,
        description="Override the utm_campaign slug (defaults to campaign name slug)",
    )

    @field_validator("product_page_url", "checkout_url", "success_url", mode="before")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def at_least_one_url(self) -> "UTMGenerateRequest":
        if not any([self.product_page_url, self.checkout_url, self.success_url]):
            raise ValueError("At least one page URL (product, checkout, or success) is required")
        return self


class CampaignUTMResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    utm_source: str
    utm_medium: str
    utm_campaign: str
    product_page_url: str | None
    checkout_url: str | None
    success_url: str | None
    product_page_utm_url: str | None
    checkout_utm_url: str | None
    success_utm_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdCampaignResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None
    meta_campaign_id: str | None
    meta_ad_set_id: str | None
    is_attora_managed: bool
    product_id: uuid.UUID | None
    is_active: bool
    utm: CampaignUTMResponse | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
