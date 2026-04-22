"""
Attora — Fallback Response System

Pre-written safe responses for scenarios where the AI engine cannot generate
a response (timeout, error, compliance violation, etc.). Returns ManyChat-
formatted responses that are always safe to send.
"""

from __future__ import annotations

import logging
from enum import Enum

from app.schemas.ai_engine import AIResponse
from app.schemas.manychat import ManyChatWebhookResponse

logger = logging.getLogger(__name__)


class FallbackType(str, Enum):
    """Categories of fallback responses."""

    GREETING = "greeting"
    TIMEOUT = "timeout"
    BUYING_TIME = "buying_time"
    ERROR = "error"
    HUMAN_HANDOFF = "human_handoff"
    COMPLIANCE_VIOLATION = "compliance_violation"
    SPAM = "spam"
    OFF_TOPIC = "off_topic"


# ── Pre-written fallback responses ─────────────────────────────

_FALLBACK_RESPONSES: dict[FallbackType, dict] = {
    FallbackType.GREETING: {
        "text": "Hey! What are you looking to work on — energy, weight, hormones?",
        "quick_replies": ["Tell me about your products", "I have a question", "Talk to a human"],
    },
    FallbackType.TIMEOUT: {
        "text": "Thanks for your message! Let me look into that for you. I'll have an answer in just a moment.",
        "quick_replies": ["Take your time", "Can I talk to someone?"],
    },
    FallbackType.BUYING_TIME: {
        "text": "Give me one sec, looking that up for you!",
        "quick_replies": ["Sure, no rush", "I have another question"],
    },
    FallbackType.ERROR: {
        "text": "I appreciate your patience! I'm having a brief technical hiccup. Could you try sending your message again in a moment?",
        "quick_replies": ["Try again", "Talk to a human"],
    },
    FallbackType.HUMAN_HANDOFF: {
        "text": "I want to make sure you get the best help possible. Let me connect you with a team member who can assist you directly.",
        "quick_replies": ["Yes, connect me", "I'll wait"],
    },
    FallbackType.COMPLIANCE_VIOLATION: {
        "text": "That's a great question! For detailed information on that topic, I'd recommend speaking with one of our team members who can give you the most accurate guidance.",
        "quick_replies": ["Connect me with someone", "I have another question"],
    },
    FallbackType.SPAM: {
        "text": "Thanks for your message! Is there something specific I can help you with regarding our products or services?",
        "quick_replies": ["Tell me about your products", "I have a question"],
    },
    FallbackType.OFF_TOPIC: {
        "text": "I appreciate the conversation! I'm best at helping with questions about our products and services. Is there anything specific I can help you with?",
        "quick_replies": ["Show me products", "I have a question", "Talk to a human"],
    },
}


def get_fallback_response(
    fallback_type: FallbackType,
    custom_greeting: str | None = None,
    custom_fallback: str | None = None,
) -> AIResponse:
    """
    Get a pre-written safe fallback response.

    Args:
        fallback_type: The type of fallback scenario.
        custom_greeting: Custom greeting from AIConfig (overrides default).
        custom_fallback: Custom fallback from AIConfig (overrides default).

    Returns:
        AIResponse with safe fallback content.
    """
    fallback = _FALLBACK_RESPONSES.get(
        fallback_type, _FALLBACK_RESPONSES[FallbackType.ERROR]
    )

    text = fallback["text"]
    quick_replies = fallback.get("quick_replies", [])

    # Use custom messages if configured
    if fallback_type == FallbackType.GREETING and custom_greeting:
        text = custom_greeting
    elif fallback_type in (FallbackType.ERROR, FallbackType.TIMEOUT) and custom_fallback:
        text = custom_fallback

    needs_handoff = fallback_type in (
        FallbackType.HUMAN_HANDOFF,
        FallbackType.COMPLIANCE_VIOLATION,
    )

    return AIResponse(
        response_text=text,
        buyer_stage="awareness",
        suggested_quick_replies=quick_replies,
        needs_human_handoff=needs_handoff,
        handoff_reason=fallback_type.value if needs_handoff else None,
        model_used="fallback",
    )


def get_fallback_manychat_response(
    fallback_type: FallbackType,
    custom_greeting: str | None = None,
    custom_fallback: str | None = None,
) -> ManyChatWebhookResponse:
    """
    Get a pre-written fallback as a ManyChat v2 response.

    Convenience wrapper for webhook endpoint use.
    """
    ai_response = get_fallback_response(
        fallback_type,
        custom_greeting=custom_greeting,
        custom_fallback=custom_fallback,
    )
    return ManyChatWebhookResponse.from_ai_response(
        response_text=ai_response.response_text,
        quick_replies=ai_response.suggested_quick_replies,
    )
