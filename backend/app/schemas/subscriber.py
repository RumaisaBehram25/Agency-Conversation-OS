"""
Attora — Subscriber Pydantic Schemas

Request/response models for subscriber/lead list and detail endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SubscriberUpdate(BaseModel):
    attora_campaign_id: UUID | None = None
    is_converted: bool | None = None
    conversion_value: float | None = None


class SubscriberConversationSummary(BaseModel):
    """Minimal conversation info embedded in subscriber detail."""

    id: UUID
    channel: str
    status: str
    message_count: int
    started_at: datetime | None = None
    last_activity_at: datetime | None = None

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

    # Activity
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    total_messages: int

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Related
    conversations: list[SubscriberConversationSummary] = []

    model_config = {"from_attributes": True}
