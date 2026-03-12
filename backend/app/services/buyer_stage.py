"""
Attora — Buyer Stage Classification Engine

Classifies subscribers into buyer journey stages based on conversation
history, current message intent, and subscriber profile. Detects stage
transitions and produces signals for tracking.

Stages: awareness -> consideration -> intent -> purchase -> post_purchase
"""

from __future__ import annotations

import logging

from app.schemas.ai_engine import (
    BuyerStageResult,
    ClassificationResult,
    ConversationContext,
    IntentType,
)

logger = logging.getLogger(__name__)

# Stage progression order (lower index = earlier in journey)
_STAGE_ORDER = [
    "awareness",
    "consideration",
    "intent",
    "purchase",
    "post_purchase",
]

# Intent-to-stage signal mapping
_INTENT_STAGE_SIGNALS: dict[str, dict] = {
    IntentType.GREETING.value: {
        "suggested_stage": "awareness",
        "signal": "initial_contact",
    },
    IntentType.BROWSING.value: {
        "suggested_stage": "awareness",
        "signal": "browsing_products",
    },
    IntentType.QUESTION.value: {
        "suggested_stage": "consideration",
        "signal": "asking_questions",
    },
    IntentType.OBJECTION.value: {
        "suggested_stage": "consideration",
        "signal": "raising_objections",
    },
    IntentType.PURCHASE_INTENT.value: {
        "suggested_stage": "intent",
        "signal": "expressed_purchase_intent",
    },
    IntentType.SUPPORT.value: {
        "suggested_stage": "post_purchase",
        "signal": "requesting_support",
    },
    IntentType.OFF_TOPIC.value: {
        "suggested_stage": None,  # Don't change stage
        "signal": "off_topic_message",
    },
    IntentType.SPAM.value: {
        "suggested_stage": None,  # Don't change stage
        "signal": "spam_detected",
    },
}

# Keywords that indicate specific stages
_STAGE_KEYWORDS: dict[str, list[str]] = {
    "consideration": [
        "compare", "comparison", "vs", "versus", "alternative",
        "features", "benefits", "how does", "what about", "tell me more",
        "difference", "better than",
    ],
    "intent": [
        "buy", "purchase", "order", "checkout", "sign up", "register",
        "how do i get", "ready to", "let's do it", "i want", "i'd like",
        "pricing", "discount", "promo", "coupon", "deal",
    ],
    "purchase": [
        "just bought", "purchased", "ordered", "signed up",
        "confirmation", "receipt", "invoice", "payment made",
    ],
    "post_purchase": [
        "refund", "return", "exchange", "issue with", "problem with",
        "not working", "broken", "disappointed", "complaint",
        "tracking", "delivery", "shipping",
    ],
}


def classify_buyer_stage(
    context: ConversationContext,
    classification: ClassificationResult,
    ai_buyer_stage: str | None = None,
) -> BuyerStageResult:
    """
    Classify the subscriber's buyer stage.

    Uses multiple signals:
    1. AI's own assessment (from response_generator, if available)
    2. Intent classification signals
    3. Keyword detection in the current message
    4. Conversation history length and patterns
    5. Current subscriber stage (stages generally only move forward)

    Args:
        context: Full conversation context.
        classification: Intent classification result.
        ai_buyer_stage: Stage suggested by the AI response generator.

    Returns:
        BuyerStageResult with new stage, transition flag, and signals.
    """
    current_stage = context.subscriber.buyer_stage
    signals: list[str] = []

    # ── Signal 1: AI's assessment ──────────────────────────────
    ai_suggested = None
    if ai_buyer_stage and ai_buyer_stage in _STAGE_ORDER:
        ai_suggested = ai_buyer_stage
        signals.append(f"ai_assessed:{ai_buyer_stage}")

    # ── Signal 2: Intent classification ────────────────────────
    intent_info = _INTENT_STAGE_SIGNALS.get(classification.intent.value)
    intent_suggested = None
    if intent_info:
        signals.append(intent_info["signal"])
        if intent_info["suggested_stage"]:
            intent_suggested = intent_info["suggested_stage"]

    # ── Signal 3: Keyword detection ────────────────────────────
    keyword_suggested = _detect_stage_keywords(context.current_message)
    if keyword_suggested:
        signals.append(f"keyword_match:{keyword_suggested}")

    # ── Signal 4: Conversation depth ───────────────────────────
    msg_count = context.message_count
    if msg_count >= 10:
        signals.append("deep_conversation")
    elif msg_count >= 5:
        signals.append("engaged_conversation")

    # ── Determine new stage ────────────────────────────────────
    # Collect all suggested stages and pick the most advanced one
    # that represents a forward movement (stages don't go backward
    # except for post_purchase which is a special case)
    candidates: list[str] = []
    if ai_suggested:
        candidates.append(ai_suggested)
    if intent_suggested:
        candidates.append(intent_suggested)
    if keyword_suggested:
        candidates.append(keyword_suggested)

    new_stage = _resolve_stage(current_stage, candidates, msg_count)
    stage_changed = new_stage != current_stage

    if stage_changed:
        signals.append(f"stage_transition:{current_stage}->{new_stage}")
        logger.info(
            f"Buyer stage transition for subscriber {context.subscriber.subscriber_id}: "
            f"{current_stage} -> {new_stage} (signals: {signals})"
        )

    # Calculate confidence
    confidence = _calculate_confidence(candidates, new_stage, classification.confidence)

    return BuyerStageResult(
        stage=new_stage,
        previous_stage=current_stage,
        stage_changed=stage_changed,
        confidence=confidence,
        signals=signals,
    )


def _detect_stage_keywords(message: str) -> str | None:
    """Detect buyer stage from message keywords."""
    msg_lower = message.lower()

    # Check stages in reverse order (most advanced first)
    for stage in reversed(_STAGE_ORDER):
        keywords = _STAGE_KEYWORDS.get(stage, [])
        for keyword in keywords:
            if keyword in msg_lower:
                return stage

    return None


def _resolve_stage(
    current_stage: str,
    candidates: list[str],
    message_count: int,
) -> str:
    """
    Resolve the final buyer stage from candidates.

    Rules:
    - Stages generally only move forward (awareness -> ... -> post_purchase)
    - Exception: post_purchase can be reached from any stage
    - If no candidates suggest a change, keep current stage
    - Conversation depth can nudge from awareness to consideration
    """
    if not candidates:
        # No signals — nudge based on conversation depth
        if current_stage == "awareness" and message_count >= 4:
            return "consideration"
        return current_stage

    current_idx = _stage_index(current_stage)

    # Find the most advanced candidate
    best_candidate = current_stage
    best_idx = current_idx

    for candidate in candidates:
        cand_idx = _stage_index(candidate)

        # post_purchase is special — allow transition from any stage
        if candidate == "post_purchase":
            best_candidate = candidate
            best_idx = cand_idx
            break

        # Only allow forward movement
        if cand_idx > best_idx:
            best_candidate = candidate
            best_idx = cand_idx

    return best_candidate


def _stage_index(stage: str) -> int:
    """Get the numeric index of a stage in the progression."""
    try:
        return _STAGE_ORDER.index(stage)
    except ValueError:
        return 0  # Default to awareness


def _calculate_confidence(
    candidates: list[str],
    resolved_stage: str,
    classifier_confidence: float,
) -> float:
    """Calculate confidence in the stage classification."""
    if not candidates:
        return 0.3  # Low confidence — no explicit signals

    # Count how many candidates agree with the resolved stage
    agreement = sum(1 for c in candidates if c == resolved_stage)
    agreement_ratio = agreement / len(candidates)

    # Blend with classifier confidence
    return min(1.0, (agreement_ratio * 0.6) + (classifier_confidence * 0.4))
