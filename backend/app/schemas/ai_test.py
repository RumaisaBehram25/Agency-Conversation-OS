"""
Request / response schemas for the AI testing playground.

Lets admins simulate a conversation with the AI without needing ManyChat
to be wired up. Exercises the same pipeline as the real webhook.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AITestChatRequest(BaseModel):
    """Payload for POST /api/ai-test/chat."""

    subscriber_id: str = Field(
        "attora_test",
        min_length=1,
        max_length=255,
        description=(
            "Test subscriber id. Auto-created if it doesn't exist in this org. "
            "Prefix with 'attora_test_' for easy filtering in analytics."
        ),
    )
    message: str = Field(..., min_length=1, max_length=4000)
    channel: str = Field(
        "messenger",
        description="Messaging channel: messenger, instagram, whatsapp.",
    )
    custom_fields: dict[str, Any] | None = Field(
        None,
        description=(
            "Optional ManyChat-style custom fields (e.g. campaign_id, ad_id, "
            "ctwa_clid) to simulate different attribution scenarios."
        ),
    )


class AITestChatResponse(BaseModel):
    response_text: str
    buyer_stage: str
    model_used: str | None = None
    response_time_ms: int | None = None
    quick_replies: list[str] = Field(default_factory=list)
    conversion_ready: bool = False
    needs_human_handoff: bool = False
    handoff_reason: str | None = None
    compliance_flags: list[str] = Field(default_factory=list)
    attora_campaign_id: str | None = None
    subscriber_tagged_urls: dict[str, str] = Field(default_factory=dict)


class AITestResetRequest(BaseModel):
    subscriber_id: str = Field("attora_test", min_length=1, max_length=255)


class AITestResetResponse(BaseModel):
    deleted_conversations: int
    deleted_messages: int
    subscriber_reset: bool
