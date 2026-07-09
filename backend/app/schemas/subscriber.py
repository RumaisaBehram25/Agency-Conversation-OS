"""
Attora — Subscriber Pydantic Schemas

Request/response models for subscriber/lead list and detail endpoints.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SubscriberConversationSummary(BaseModel):
    """Minimal conversation info embedded in subscriber detail."""

    id: UUID
    channel: str
    status: str
    message_count: int
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    summary: str | None = None
    closed_at: datetime | None = None
    follow_up_attempts: int = 0
    last_follow_up_at: datetime | None = None

    model_config = {"from_attributes": True}


class SubscriberListItem(BaseModel):
    """Single item in the subscribers list."""

    id: UUID
    first_name: str | None = None
    last_name: str | None = None
    channel: str
    buyer_stage: str
    is_converted: bool
    conversion_value: float | None = None
    total_messages: int
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    created_at: datetime
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    hyros_purchased: bool = False
    hyros_product: str | None = None
    hyros_synced_at: datetime | None = None

    model_config = {"from_attributes": True}


class SubscriberDetail(BaseModel):
    """Full subscriber detail with conversations and conversion data."""

    id: UUID
    manychat_subscriber_id: str
    channel: str

    # Identity
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None

    # AI context
    buyer_stage: str
    interests: list[str] | None = None
    objections_raised: list[str] | None = None
    conversation_summary: str | None = None

    # Conversion
    is_converted: bool
    conversion_value: float | None = None
    converted_at: datetime | None = None
    hyros_purchased: bool = False
    hyros_product: str | None = None
    hyros_purchase_date: datetime | None = None
    hyros_lead_id: str | None = None
    hyros_email: str | None = None
    hyros_origin_source: str | None = None
    hyros_origin_tag: str | None = None
    hyros_traffic_source: str | None = None
    hyros_creative_name: str | None = None
    hyros_synced_at: datetime | None = None

    # Activity
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    total_messages: int

    # First-touch UTMs (intake)
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None

    # Meta / intake attribution (ManyChat custom fields)
    ctwa_clid: str | None = None
    ad_id: str | None = None
    post_id: str | None = None
    ad_set_id: str | None = None
    campaign_id: str | None = None
    attora_campaign_id: UUID | None = None

    # Activity (follow-up silence anchor)
    last_user_message_at: datetime | None = None

    # AI session log (JSON); may be large — surfaced for ops visibility
    history: Any = Field(default=None, description="Structured session history JSON")

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Related
    conversations: list[SubscriberConversationSummary] = []

    model_config = {"from_attributes": True}
