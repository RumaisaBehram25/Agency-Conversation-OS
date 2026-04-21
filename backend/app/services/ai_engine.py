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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import AdCampaign
from app.schemas.ai_engine import AIResponse, IntentType
from app.schemas.campaign import build_utm_url
from app.services.buyer_stage import classify_buyer_stage
from app.services.classifier import classify_message
from app.services.config_loader import load_org_config
from app.services.context_manager import (
    load_conversation_context,
    store_message_and_update_context,
)
from app.services.fallback import FallbackType, get_fallback_response
from app.services.knowledge_retriever import retrieve_knowledge
from app.services.output_validator import validate_output
from app.services.response_generator import generate_response

logger = logging.getLogger(__name__)

# Total pipeline time budget
_TOTAL_TIMEOUT_SECONDS = 10.0


async def _load_subscriber_tagged_urls(
    db: AsyncSession | None,
    org_id: uuid.UUID,
    attora_campaign_id: str | None,
    subscriber_id: str,
) -> dict[str, str]:
    """
    Look up the campaign's UTM URLs and stamp attora_sub=<subscriber_id> on each.

    Returns a dict with keys "product_page", "checkout", "success" — only entries
    with a configured URL are included. Non-fatal on any failure; returns {}.
    """
    if db is None or not attora_campaign_id:
        return {}
    try:
        campaign_uuid = uuid.UUID(attora_campaign_id)
    except (ValueError, TypeError):
        return {}

    try:
        result = await db.execute(
            select(AdCampaign)
            .where(AdCampaign.id == campaign_uuid, AdCampaign.org_id == org_id)
            .options(selectinload(AdCampaign.utm))
        )
        campaign = result.scalar_one_or_none()
        if campaign is None or campaign.utm is None:
            return {}

        extra = {"attora_sub": subscriber_id}
        tagged: dict[str, str] = {}
        if campaign.utm.product_page_utm_url:
            tagged["product_page"] = build_utm_url(
                campaign.utm.product_page_utm_url, extra
            )
        if campaign.utm.checkout_utm_url:
            tagged["checkout"] = build_utm_url(campaign.utm.checkout_utm_url, extra)
        if campaign.utm.success_utm_url:
            tagged["success"] = build_utm_url(campaign.utm.success_utm_url, extra)
        return tagged
    except Exception as e:
        logger.warning(
            "Failed to load per-subscriber UTM URLs for campaign %s: %s",
            attora_campaign_id,
            e,
        )
        return {}


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
    Main AI engine entry point — orchestrates the full conversation pipeline.

    Args:
        org_id: Organization UUID.
        subscriber_id: ManyChat subscriber ID string.
        message: The user's message text.
        channel: Messaging channel (whatsapp, messenger, instagram).
        custom_fields: ManyChat custom fields dict.
        db: Async database session.
        redis_client: Optional Redis client.

    Returns:
        AIResponse with the generated response and metadata.
    """
    pipeline_start = time.monotonic()
    custom_fields = custom_fields or {}

    try:
        return await asyncio.wait_for(
            _run_pipeline(
                org_id=org_id,
                subscriber_id=subscriber_id,
                message=message,
                channel=channel,
                custom_fields=custom_fields,
                db=db,
                redis_client=redis_client,
                pipeline_start=pipeline_start,
            ),
            timeout=_TOTAL_TIMEOUT_SECONDS,
        )
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

    # ── Step 2.1: Stamp per-subscriber UTM URLs ────────────────
    # So the AI can quote an attribution link scoped to THIS lead.
    context.subscriber_tagged_urls = await _load_subscriber_tagged_urls(
        db=db,
        org_id=org_id,
        attora_campaign_id=context.subscriber.attora_campaign_id,
        subscriber_id=subscriber_id,
    )

    # ── Step 2.5: Retrieve knowledge (<1s via Haiku) ──────────
    if db is not None:
        try:
            step_start = time.monotonic()
            knowledge = await retrieve_knowledge(
                message=message,
                buyer_stage=context.subscriber.buyer_stage,
                db=db,
            )
            context.retrieved_knowledge = knowledge
            logger.debug(
                f"Step 2.5 (knowledge): {int((time.monotonic() - step_start) * 1000)}ms "
                f"docs={len(knowledge)}"
            )
        except Exception as e:
            logger.error(f"Knowledge retrieval failed, continuing pipeline: {e}")

    # ── Step 3: Classify intent (<500ms via Haiku) ─────────────
    step_start = time.monotonic()
    subscriber_brief = (
        f"Stage: {context.subscriber.buyer_stage}, "
        f"Messages: {context.subscriber.total_messages}"
    )
    classification = await classify_message(message, subscriber_brief)
    logger.debug(
        f"Step 3 (classify): {int((time.monotonic() - step_start) * 1000)}ms "
        f"intent={classification.intent}"
    )

    # ── Step 4: Route — simple or complex ──────────────────────
    if classification.is_simple:
        ai_response = _route_simple_intent(
            classification.intent, org_config, context
        )
        if ai_response:
            ai_response.response_time_ms = int(
                (time.monotonic() - pipeline_start) * 1000
            )
            # Fire-and-forget: store and update
            asyncio.create_task(
                store_message_and_update_context(
                    context=context,
                    user_message=message,
                    ai_response=ai_response,
                    redis_client=redis_client,
                    classifier_usage=classification.usage,
                )
            )
            return ai_response

    # ── Step 5: Generate response (<7s via Sonnet) ─────────────
    step_start = time.monotonic()
    try:
        ai_response = await generate_response(context, org_config)
    except asyncio.TimeoutError:
        logger.warning("Sonnet generation timed out, using fallback")
        return get_fallback_response(
            FallbackType.BUYING_TIME,
            custom_fallback=org_config.ai_config.fallback_message,
        )
    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        return get_fallback_response(
            FallbackType.ERROR,
            custom_fallback=org_config.ai_config.fallback_message,
        )
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
    asyncio.create_task(
        store_message_and_update_context(
            context=context,
            user_message=message,
            ai_response=ai_response,
            redis_client=redis_client,
            classifier_usage=classification.usage,
        )
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
