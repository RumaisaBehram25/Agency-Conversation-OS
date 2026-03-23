"""
Attora — Conversation Pydantic Schemas

Request/response models for conversation list and detail endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Individual message in a conversation."""

    id: UUID
    sender: str
    content: str
    intent_signals: list[str] | None = None
    buyer_stage_at_time: str | None = None
    compliance_flags: list[str] | None = None
    ai_model: str | None = None
    ai_response_time_ms: int | None = None
    ai_tokens_used: int | None = None
    quick_replies: list[str] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationSubscriberInfo(BaseModel):
    """Minimal subscriber info embedded in conversation responses."""

    id: UUID
    first_name: str | None = None
    last_name: str | None = None
    channel: str
    buyer_stage: str

    model_config = {"from_attributes": True}


class ConversationListItem(BaseModel):
    """Single item in the conversations list."""

    id: UUID
    subscriber_id: UUID
    subscriber_name: str | None = None
    channel: str
    status: str
    buyer_stage: str | None = None
    message_count: int
    last_message_preview: str | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    """Full conversation detail with messages and subscriber info."""

    id: UUID
    subscriber_id: UUID
    channel: str
    status: str
    summary: str | None = None
    message_count: int
    ai_response_time_avg_ms: int | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    subscriber: ConversationSubscriberInfo | None = None
    messages: list[MessageResponse] = []

    model_config = {"from_attributes": True}
