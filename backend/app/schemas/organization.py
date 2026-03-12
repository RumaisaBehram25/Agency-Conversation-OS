"""
Attora — Organization Pydantic Schemas

Request/response models for organization CRUD endpoints.
Sensitive fields are masked in responses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    """POST /api/organizations — Create a new organization."""
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")

    # Optional ManyChat config (can be added later)
    manychat_api_key: str | None = None
    manychat_page_id: str | None = None
    manychat_account_id: str | None = None

    # Optional Meta config (can be added later)
    meta_pixel_id: str | None = None
    meta_capi_token: str | None = None
    meta_ad_account_id: str | None = None
    meta_page_id: str | None = None
    meta_business_manager_id: str | None = None

    # Plan
    plan: str = "starter"
    monthly_conversation_limit: int = 1000


class OrganizationUpdate(BaseModel):
    """PUT /api/organizations/{org_id} — Update organization fields."""
    name: str | None = Field(None, min_length=1, max_length=255)

    # ManyChat config
    manychat_api_key: str | None = None
    manychat_page_id: str | None = None
    manychat_account_id: str | None = None

    # Meta config
    meta_pixel_id: str | None = None
    meta_capi_token: str | None = None
    meta_ad_account_id: str | None = None
    meta_page_id: str | None = None
    meta_business_manager_id: str | None = None

    # Plan
    plan: str | None = None
    monthly_conversation_limit: int | None = None


class OrganizationResponse(BaseModel):
    """Organization data returned in API responses. Sensitive fields are masked."""
    id: UUID
    name: str
    slug: str

    # ManyChat config (API key masked)
    manychat_api_key: str | None = None  # masked
    manychat_page_id: str | None = None
    manychat_account_id: str | None = None

    # Meta config (CAPI token masked)
    meta_pixel_id: str | None = None
    meta_capi_token: str | None = None  # masked
    meta_ad_account_id: str | None = None
    meta_page_id: str | None = None
    meta_business_manager_id: str | None = None

    # Attora API key (masked)
    attora_api_key: str | None = None  # masked

    # Plan
    plan: str
    monthly_conversation_limit: int

    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
