"""
Attora — Intent Classifier

Uses Claude Haiku (claude-haiku-4-5-20251001) to classify user messages
into intent categories, detect language and sentiment, and determine
whether a simple cached response suffices.

Budget: 500ms max.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import anthropic

from app.config import settings
from app.schemas.ai_engine import (
    ClassificationResult,
    IntentType,
    Sentiment,
    TokenUsage,
)

logger = logging.getLogger(__name__)

# Model configuration
_CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"
_CLASSIFIER_TIMEOUT_SECONDS = 0.5  # 500ms budget
_MAX_TOKENS = 256

# Classification system prompt
_CLASSIFIER_SYSTEM_PROMPT = """You are a message intent classifier for a sales AI assistant. Analyze the user's message and classify it.

You MUST respond with valid JSON only. No other text.

```json
{
  "intent": "question|objection|purchase_intent|browsing|support|off_topic|greeting|spam",
  "language": "en",
  "sentiment": "positive|neutral|negative",
  "is_simple": false,
  "confidence": 0.9
}
```

INTENT DEFINITIONS:
- greeting: Hello, hi, hey, good morning, etc.
- question: Asking about products, services, features, pricing.
- objection: Expressing concerns, hesitations, price complaints, competitor comparisons.
- purchase_intent: Expressing desire to buy, asking how to order, requesting checkout link.
- browsing: Casual exploration, "just looking", vague interest.
- support: Post-purchase help, issues with existing order, account problems.
- off_topic: Unrelated to products/services (weather, politics, random chat).
- spam: Promotional content, bot-like messages, gibberish.

is_simple RULES:
- Set true for: greetings, simple thank-you messages, one-word acknowledgments, spam, off_topic
- Set false for: questions, objections, purchase_intent, complex support requests

LANGUAGE: Use ISO 639-1 codes (en, es, pt, fr, etc.)
CONFIDENCE: 0.0 to 1.0 — how confident you are in the classification."""


async def classify_message(
    message: str,
    subscriber_context: str | None = None,
) -> ClassificationResult:
    """
    Classify a user message using Claude Haiku.

    Args:
        message: The user's message text.
        subscriber_context: Optional brief context about the subscriber.

    Returns:
        ClassificationResult with intent, language, sentiment, is_simple.

    Falls back to a safe default classification on timeout or error.
    """
    start_time = time.monotonic()

    user_content = f"Classify this message:\n\n{message}"
    if subscriber_context:
        user_content = f"Subscriber context: {subscriber_context}\n\n{user_content}"

    try:
        result = await asyncio.wait_for(
            _call_haiku_classifier(user_content),
            timeout=_CLASSIFIER_TIMEOUT_SECONDS,
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.debug(
            f"Classification completed in {elapsed_ms}ms: "
            f"intent={result.intent}, is_simple={result.is_simple}"
        )
        return result

    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.warning(f"Classifier timeout after {elapsed_ms}ms, using fallback")
        return _fallback_classification(message)

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(f"Classifier error after {elapsed_ms}ms: {e}")
        return _fallback_classification(message)


async def _call_haiku_classifier(user_content: str) -> ClassificationResult:
    """Make the actual API call to Claude Haiku."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=_CLASSIFIER_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_CLASSIFIER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    usage = _extract_usage(response)

    # Parse JSON from response
    raw_text = response.content[0].text.strip()

    # Handle potential markdown code block wrapping
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Remove first and last lines (``` markers)
        raw_text = "\n".join(lines[1:-1]) if len(lines) > 2 else raw_text

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning(f"Classifier returned invalid JSON: {raw_text[:200]}")
        return _fallback_classification("")

    # Map to enum values safely
    intent_str = data.get("intent", "browsing")
    try:
        intent = IntentType(intent_str)
    except ValueError:
        intent = IntentType.BROWSING

    sentiment_str = data.get("sentiment", "neutral")
    try:
        sentiment = Sentiment(sentiment_str)
    except ValueError:
        sentiment = Sentiment.NEUTRAL

    return ClassificationResult(
        intent=intent,
        language=data.get("language", "en"),
        sentiment=sentiment,
        is_simple=data.get("is_simple", False),
        confidence=min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
        usage=usage,
    )


def _extract_usage(response) -> TokenUsage:
    u = getattr(response, "usage", None)
    if u is None:
        return TokenUsage(model=_CLASSIFIER_MODEL)
    return TokenUsage(
        model=_CLASSIFIER_MODEL,
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


def _fallback_classification(message: str) -> ClassificationResult:
    """
    Rule-based fallback classification when Haiku is unavailable.

    Uses simple heuristics to provide a reasonable classification.
    """
    msg_lower = message.strip().lower()

    # Greeting detection
    greetings = {"hi", "hello", "hey", "hola", "good morning", "good afternoon",
                 "good evening", "sup", "yo", "howdy", "hiya"}
    if msg_lower in greetings or any(msg_lower.startswith(g) for g in greetings):
        return ClassificationResult(
            intent=IntentType.GREETING,
            is_simple=True,
            confidence=0.7,
        )

    # Purchase intent signals
    purchase_words = {"buy", "purchase", "order", "checkout", "price", "cost",
                      "how much", "payment", "pay"}
    if any(word in msg_lower for word in purchase_words):
        return ClassificationResult(
            intent=IntentType.PURCHASE_INTENT,
            is_simple=False,
            confidence=0.5,
        )

    # Very short messages are likely simple
    if len(msg_lower) < 5:
        return ClassificationResult(
            intent=IntentType.BROWSING,
            is_simple=True,
            confidence=0.4,
        )

    # Default to browsing (requires full Sonnet response)
    return ClassificationResult(
        intent=IntentType.BROWSING,
        is_simple=False,
        confidence=0.3,
    )
