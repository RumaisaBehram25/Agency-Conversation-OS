"""
Attora — AI Engine Orchestrator

Main orchestrator for the AI conversation pipeline. Receives a message
and returns a structured AI response within a 10-second time budget.

Pipeline:
1. Load client config (config_loader) — <100ms
2. Load conversation context (context_manager) — <200ms
3. Classify intent (classifier) — <500ms via Haiku
4. Route: simple intent -> cached response, complex -> Sonnet
5. Generate response (response_generator) — <7s via Sonnet
6. Validate output (output_validator) — <50ms
7. Fire-and-forget: store message, update context, fire CAPI if conversion
8. Return structured response
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ai_engine import AIResponse, IntentType
from app.services.buyer_stage import classify_buyer_stage
from app.services.classifier import classify_message
from app.services.config_loader import load_org_config
from app.services.context_manager import (
    load_conversation_context,
    store_message_and_update_context,
)
from app.services.fallback import FallbackType, get_fallback_response
from app.services.output_validator import validate_output
from app.services.response_generator import generate_response

logger = logging.getLogger(__name__)

# Total pipeline time budget
_TOTAL_TIMEOUT_SECONDS = 10.0


def _log_background_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception:
        logger.exception("Background message writer failed")


def _schedule_message_persistence(
    context,
    message: str,
    ai_response: AIResponse,
    redis_client,
) -> None:
    logger.info(
        "Scheduling background message writer conversation_id=%s",
        context.conversation_id,
    )
    task = asyncio.create_task(
        store_message_and_update_context(
            context=context,
            user_message=message,
            ai_response=ai_response,
            redis_client=redis_client,
        )
    )
    task.add_done_callback(_log_background_task_result)


async def process_message(
    org_id: uuid.UUID,
    subscriber_id: str,
    message: str,
    channel: str,
    custom_fields: dict | None = None,
    db: AsyncSession | None = None,
    redis_client=None,
) -> AIResponse:
    """
    Backwards-compatible wrapper for legacy callers.

    Delegates to generate_ai_response so timeout/fallback/latency behavior
    is centralized in one entrypoint.
    """
    return await generate_ai_response(
        text=message,
        subscriber_id=subscriber_id,
        org_id=org_id,
        channel=channel,
        custom_fields=custom_fields,
        db=db,
        redis_client=redis_client,
    )


async def generate_ai_response(
    text: str,
    subscriber_id: str,
    *,
    org_id: uuid.UUID,
    channel: str,
    custom_fields: dict | None = None,
    db: AsyncSession | None = None,
    redis_client=None,
) -> AIResponse:
    """
    Main AI pipeline entrypoint for webhook and service callers.

    This function isolates all external AI behavior behind a single boundary,
    applies timeout handling, and always returns a safe fallback response on
    failure.

    Args:
        text: The user's message text.
        subscriber_id: ManyChat subscriber ID string.
        org_id: Organization UUID.
        channel: Messaging channel (whatsapp, messenger, instagram).
        custom_fields: ManyChat custom fields dict.
        db: Async database session.
        redis_client: Optional Redis client.

    Returns:
        AIResponse with the generated response and metadata.
    """
    pipeline_start = time.monotonic()
    custom_fields = custom_fields or {}
    safe_text = (text or "").strip()

    logger.info(
        "AI request start org=%s subscriber=%s channel=%s message_length=%s",
        org_id,
        subscriber_id,
        channel,
        len(safe_text),
    )

    if not safe_text:
        logger.warning(
            "AI request received empty text org=%s subscriber=%s",
            org_id,
            subscriber_id,
        )
        return get_fallback_response(FallbackType.ERROR)

    try:
        response = await asyncio.wait_for(
            _run_pipeline(
                org_id=org_id,
                subscriber_id=subscriber_id,
                message=safe_text,
                channel=channel,
                custom_fields=custom_fields,
                db=db,
                redis_client=redis_client,
                pipeline_start=pipeline_start,
            ),
            timeout=_TOTAL_TIMEOUT_SECONDS,
        )
        elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
        logger.info(
            "AI request complete in %sms org=%s subscriber=%s model=%s",
            elapsed_ms,
            org_id,
            subscriber_id,
            response.model_used,
        )
        return response
    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
        logger.warning(f"Pipeline timeout after {elapsed_ms}ms for org={org_id}")
        return get_fallback_response(FallbackType.BUYING_TIME)
    except Exception as e:
        elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
        logger.error(
            f"Pipeline error after {elapsed_ms}ms for org={org_id}: {e}",
            exc_info=True,
        )
        return get_fallback_response(FallbackType.ERROR)


async def _run_pipeline(
    org_id: uuid.UUID,
    subscriber_id: str,
    message: str,
    channel: str,
    custom_fields: dict,
    db: AsyncSession | None,
    redis_client,
    pipeline_start: float,
) -> AIResponse:
    """Internal pipeline execution (wrapped by timeout in process_message)."""

    # ── Step 1: Load client config (<100ms) ────────────────────
    step_start = time.monotonic()
    org_config = await load_org_config(org_id, db, redis_client)
    logger.debug(
        f"Step 1 (config_load): {int((time.monotonic() - step_start) * 1000)}ms"
    )

    # ── Step 2: Load conversation context (<200ms) ─────────────
    step_start = time.monotonic()
    context = await load_conversation_context(
        org_id=org_id,
        subscriber_id=subscriber_id,
        current_message=message,
        channel=channel,
        custom_fields=custom_fields,
        db=db,
        redis_client=redis_client,
    )
    logger.debug(
        f"Step 2 (context_load): {int((time.monotonic() - step_start) * 1000)}ms"
    )

    # Persist the request-scoped subscriber/conversation writes before
    # handing off message storage to the fire-and-forget worker.
    if db is not None:
        await db.commit()

    # ── Step 3: Classify intent (<500ms via Haiku) ─────────────
    step_start = time.monotonic()
    subscriber_brief = (
        f"Stage: {context.subscriber.buyer_stage}, "
        f"Messages: {context.subscriber.total_messages}"
    )
    logger.info("🧠 Classifying intent for conversation_id=%s text=%s", context.conversation_id, message)
    classification = await classify_message(message, subscriber_brief)
    logger.debug(
        f"Step 3 (classify): {int((time.monotonic() - step_start) * 1000)}ms "
        f"intent={classification.intent}"
    )
    logger.info(
        "🧠 Classified intent conversation_id=%s intent=%s is_simple=%s confidence=%s",
        context.conversation_id,
        classification.intent,
        classification.is_simple,
        classification.confidence,
    )

    # ── Step 4: Route — simple or complex ──────────────────────
    if classification.is_simple:
        ai_response = _route_simple_intent(
            classification.intent, org_config, context
        )
        if ai_response:
            logger.info(
                "🧭 Routed simple intent conversation_id=%s intent=%s response_model=%s",
                context.conversation_id,
                classification.intent,
                ai_response.model_used,
            )
            ai_response.response_time_ms = int(
                (time.monotonic() - pipeline_start) * 1000
            )
            _schedule_message_persistence(
                context=context,
                message=message,
                ai_response=ai_response,
                redis_client=redis_client,
            )
            return ai_response

    # ── Step 5: Generate response (<7s via Sonnet) ─────────────
    step_start = time.monotonic()
    logger.info(
        "🧭 Routing to full AI generation conversation_id=%s intent=%s",
        context.conversation_id,
        classification.intent,
    )
    try:
        ai_response = await generate_response(context, org_config)
    except asyncio.TimeoutError:
        logger.warning("Sonnet generation timed out, using fallback")
        fallback_response = get_fallback_response(
            FallbackType.BUYING_TIME,
            custom_fallback=org_config.ai_config.fallback_message,
        )
        _schedule_message_persistence(
            context=context,
            message=message,
            ai_response=fallback_response,
            redis_client=redis_client,
        )
        return fallback_response
    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        fallback_response = get_fallback_response(
            FallbackType.ERROR,
            custom_fallback=org_config.ai_config.fallback_message,
        )
        _schedule_message_persistence(
            context=context,
            message=message,
            ai_response=fallback_response,
            redis_client=redis_client,
        )
        return fallback_response
    logger.debug(
        f"Step 5 (generate): {int((time.monotonic() - step_start) * 1000)}ms"
    )

    # ── Step 6: Validate output (<50ms) ────────────────────────
    step_start = time.monotonic()
    validation = validate_output(ai_response.response_text, org_config)
    logger.debug(
        f"Step 6 (validate): {int((time.monotonic() - step_start) * 1000)}ms "
        f"valid={validation.is_valid} flags={validation.flags}"
    )

    # Apply validation results
    if not validation.is_valid:
        ai_response.response_text = validation.cleaned_text
        ai_response.compliance_flags = validation.flags
    if validation.needs_human_handoff:
        ai_response.needs_human_handoff = True
        ai_response.handoff_reason = validation.handoff_reason

    # ── Buyer stage classification ─────────────────────────────
    stage_result = classify_buyer_stage(
        context=context,
        classification=classification,
        ai_buyer_stage=ai_response.buyer_stage,
    )
    ai_response.buyer_stage = stage_result.stage
    if stage_result.signals:
        ai_response.intent_signals = list(
            set(ai_response.intent_signals + stage_result.signals)
        )

    # ── Total pipeline time ────────────────────────────────────
    ai_response.response_time_ms = int(
        (time.monotonic() - pipeline_start) * 1000
    )
    logger.info(
        f"Pipeline complete in {ai_response.response_time_ms}ms "
        f"(model={ai_response.model_used}, stage={ai_response.buyer_stage}, "
        f"handoff={ai_response.needs_human_handoff})"
    )

    # ── Step 7: Fire-and-forget operations ─────────────────────
    _schedule_message_persistence(
        context=context,
        message=message,
        ai_response=ai_response,
        redis_client=redis_client,
    )

    # Fire CAPI if conversion-ready
    if ai_response.conversion_ready:
        asyncio.create_task(
            _fire_conversion_event(
                org_config=org_config,
                context=context,
                ai_response=ai_response,
            )
        )

    return ai_response


def _route_simple_intent(
    intent: IntentType,
    org_config,
    context,
) -> AIResponse | None:
    """
    Route simple intents to cached/fallback responses.

    Returns None if the intent should be handled by the full Sonnet pipeline.
    """
    if intent == IntentType.GREETING:
        return get_fallback_response(
            FallbackType.GREETING,
            custom_greeting=org_config.ai_config.greeting_message,
        )

    if intent == IntentType.SPAM:
        return get_fallback_response(FallbackType.SPAM)

    if intent == IntentType.OFF_TOPIC:
        return get_fallback_response(FallbackType.OFF_TOPIC)

    # All other intents go through the full pipeline
    return None


async def _fire_conversion_event(
    org_config,
    context,
    ai_response: AIResponse,
) -> None:
    """Fire Meta CAPI conversion event (fire-and-forget)."""
    try:
        if not org_config.meta_pixel_id or not org_config.meta_capi_token:
            logger.debug("No Meta CAPI config, skipping conversion event")
            return

        from app.integrations.meta.capi import fire_conversion_event

        await fire_conversion_event(
            pixel_id=org_config.meta_pixel_id,
            access_token=org_config.meta_capi_token,
            event_name="Lead",
            subscriber_id=context.subscriber.subscriber_id,
            channel=context.subscriber.channel,
            ctwa_clid=context.subscriber.ctwa_clid,
        )
        logger.info(
            f"CAPI Lead event fired for subscriber "
            f"{context.subscriber.subscriber_id}"
        )
    except Exception as e:
        logger.error(f"CAPI event failed: {e}", exc_info=True)
