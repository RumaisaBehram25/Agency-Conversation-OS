"""
Attora — Settings Pydantic Schemas

Request/response models for organization settings endpoints.
Sensitive fields are masked in responses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    """GET /api/settings — Organization settings with masked sensitive fields."""

    id: UUID
    name: str
    slug: str

    # ManyChat (API key masked)
    manychat_api_key: str | None = None
    manychat_page_id: str | None = None
    manychat_account_id: str | None = None
    manychat_outbound_flow_ns: str | None = None
    manychat_outbound_flow_ns_instagram: str | None = None

    # Meta (CAPI token masked)
    meta_pixel_id: str | None = None
    meta_capi_token: str | None = None
    meta_ad_account_id: str | None = None
    meta_page_id: str | None = None
    meta_business_manager_id: str | None = None

    # Hyros
    hyros_api_key: str | None = None

    # Plan
    plan: str
    monthly_conversation_limit: int

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    """PUT /api/settings — Update organization settings."""

    # ManyChat config
    manychat_api_key: str | None = None
    manychat_page_id: str | None = None
    manychat_account_id: str | None = None
    manychat_outbound_flow_ns: str | None = None
    manychat_outbound_flow_ns_instagram: str | None = None

    # Meta config
    meta_pixel_id: str | None = None
    meta_capi_token: str | None = None
    meta_ad_account_id: str | None = None
    meta_page_id: str | None = None
    meta_business_manager_id: str | None = None

    # Hyros
    hyros_api_key: str | None = None
