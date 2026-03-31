"""
Attora — AI Engine Schemas

Internal Pydantic models for the AI conversation engine pipeline.
These schemas define data flowing between the classifier, response generator,
output validator, buyer stage engine, and context manager.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


# ── Intent Classification ─────────────────────────────────────


class IntentType(str, enum.Enum):
    """Intent categories detected by the classifier."""

    QUESTION = "question"
    OBJECTION = "objection"
    PURCHASE_INTENT = "purchase_intent"
    BROWSING = "browsing"
    SUPPORT = "support"
    OFF_TOPIC = "off_topic"
    GREETING = "greeting"
    SPAM = "spam"


class Sentiment(str, enum.Enum):
    """Sentiment detected in the message."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ClassificationResult(BaseModel):
    """Output of the Haiku intent classifier."""

    intent: IntentType = Field(..., description="Primary intent of the message")
    language: str = Field(default="en", description="ISO 639-1 language code")
    sentiment: Sentiment = Field(
        default=Sentiment.NEUTRAL, description="Detected sentiment"
    )
    is_simple: bool = Field(
        default=False,
        description="Whether the intent can be served from a cached/template response",
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Classification confidence score"
    )


# ── Conversation Context ──────────────────────────────────────


class MessageContext(BaseModel):
    """A single message in conversation history for context building."""

    sender: str  # "user", "ai", "human"
    content: str
    timestamp: datetime | None = None


class SubscriberContext(BaseModel):
    """Subscriber profile data for prompt context."""

    subscriber_id: str
    first_name: str | None = None
    last_name: str | None = None
    buyer_stage: str = "awareness"
    interests: list[str] = Field(default_factory=list)
    objections_raised: list[str] = Field(default_factory=list)
    conversation_summary: str | None = None
    total_messages: int = 0
    channel: str = "messenger"
    ctwa_clid: str | None = None
    ad_id: str | None = None


class ConversationContext(BaseModel):
    """Full context object passed to the prompt builder."""

    org_id: str
    conversation_id: str | None = None
    subscriber: SubscriberContext
    history: list[MessageContext] = Field(default_factory=list)
    current_message: str
    message_count: int = 0
    retrieved_knowledge: list[str] = Field(default_factory=list)


# ── Client Configuration (cached) ────────────────────────────


class ProductInfo(BaseModel):
    """Product data for prompt context."""

    id: str
    name: str
    description: str | None = None
    price: float | None = None
    currency: str = "USD"
    checkout_url: str | None = None
    conversion_value: float | None = None
    eligibility_criteria: dict | None = None
    objection_responses: dict | None = None
    is_active: bool = True


class AIConfigData(BaseModel):
    """AI config data for prompt context."""

    brand_voice: str | None = None
    persona_name: str | None = None
    system_prompt_override: str | None = None
    product_knowledge: str | None = None
    compliance_rules: str | None = None
    conversion_playbook: str | None = None
    objection_handlers: dict | None = None
    greeting_message: str | None = None
    fallback_message: str | None = None
    max_messages_before_handoff: int = 50


class OrgConfig(BaseModel):
    """Cached organization configuration for AI engine."""

    org_id: str
    org_name: str
    org_slug: str
    meta_pixel_id: str | None = None
    meta_capi_token: str | None = None
    meta_page_id: str | None = None
    ai_config: AIConfigData = Field(default_factory=AIConfigData)
    products: list[ProductInfo] = Field(default_factory=list)


# ── AI Response ───────────────────────────────────────────────


class AIResponse(BaseModel):
    """Output of the AI engine — the full pipeline result."""

    response_text: str = Field(..., description="The AI-generated response text")
    buyer_stage: str = Field(
        default="awareness", description="Updated buyer stage"
    )
    intent_signals: list[str] = Field(
        default_factory=list, description="Detected intent signals"
    )
    conversion_ready: bool = Field(
        default=False,
        description="Whether the subscriber is ready for conversion",
    )
    suggested_quick_replies: list[str] = Field(
        default_factory=list, description="Suggested quick reply buttons"
    )
    custom_field_updates: dict[str, str] = Field(
        default_factory=dict,
        description="Custom field updates to send back to ManyChat",
    )
    compliance_flags: list[str] = Field(
        default_factory=list, description="Compliance violations detected"
    )
    model_used: str | None = Field(
        None, description="AI model used for response generation"
    )
    response_time_ms: int = Field(
        default=0, description="Total response generation time in ms"
    )
    tokens_used: int = Field(default=0, description="Total tokens consumed")
    needs_human_handoff: bool = Field(
        default=False, description="Whether a human agent should take over"
    )
    handoff_reason: str | None = Field(
        None, description="Reason for human handoff"
    )


# ── Buyer Stage ───────────────────────────────────────────────


class BuyerStageResult(BaseModel):
    """Output of the buyer stage classification engine."""

    stage: str = Field(
        default="awareness",
        description="Classified buyer stage: awareness, consideration, intent, purchase, post_purchase",
    )
    previous_stage: str | None = Field(
        None, description="Previous buyer stage before this classification"
    )
    stage_changed: bool = Field(
        default=False, description="Whether the stage transitioned"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Classification confidence"
    )
    signals: list[str] = Field(
        default_factory=list,
        description="Signals that contributed to stage classification",
    )


# ── Output Validation ─────────────────────────────────────────


class ValidationResult(BaseModel):
    """Output of the multi-layer output validator."""

    is_valid: bool = Field(
        default=True, description="Whether the response passed all validation"
    )
    original_text: str = Field(..., description="The original response text")
    cleaned_text: str = Field(
        ..., description="The cleaned/replaced response text"
    )
    flags: list[str] = Field(
        default_factory=list, description="Validation flags raised"
    )
    needs_human_handoff: bool = Field(
        default=False,
        description="Whether a kill-switch topic was detected",
    )
    handoff_reason: str | None = None
