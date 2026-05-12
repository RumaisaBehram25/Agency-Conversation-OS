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

from app.config import settings
from app.schemas.ai_engine import AIResponse, IntentType
from app.utils.dm_links import DmSubscriberView, build_dm_link
from app.services.campaign_utm_resolver import (
    dm_utm_strings_from_campaign,
    fetch_managed_campaign_with_utm,
)
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
_TOTAL_TIMEOUT_SECONDS = 15.0

_PURCHASE_LINK_HINTS = (
    "buy",
    "purchase",
    "checkout",
    "success",
    "link",
    "payment",
    "grab it",
    "how do i buy",
)

# Past-tense purchase confirmations — lead has already converted, do NOT
# inject a checkout link (would be confusing / suggest re-purchase).
_POST_PURCHASE_HINTS = (
    "i bought",
    "i just bought",
    "i purchased",
    "i just purchased",
    "just purchased",
    "got it",
    "i got it",
    "i'm in",
    "im in",
    "already bought",
    "already purchased",
    "paid for it",
    "i paid",
    "checked out",
    "completed the purchase",
)

# When the message is ONLY about price, do NOT inject a purchase link.
_PRICE_ONLY_HINTS = (
    "price",
    "cost",
    "how much",
    "pricing",
    "what does it cost",
    "what's the price",
)

_SUCCESS_LINK_HINTS = (
    "success",
    "purchase success",
    "confirmation",
    "thank you page",
)

_CHECKOUT_LINK_HINTS = (
    "checkout",
    "buy",
    "purchase",
    "payment",
    "order",
    "grab it",
)

_PRODUCT_LINK_HINTS = (
    "product",
    "products",
    "program",
    "urls",
)


async def _load_subscriber_tagged_urls(
    db: AsyncSession | None,
    org_id: uuid.UUID,
    attora_campaign_id: str | None,
    subscriber_id: str,
    attora_id: str | None = None,
) -> dict[str, str]:
    """
    Look up the campaign's UTM URLs and stamp per-subscriber attribution.

    Each returned URL carries attora_sub (ManyChat ID) and attora_id (Attora
    UUID) so the landing page can attribute the conversion back to this exact
    lead via /api/conversions/track.

    Returns a dict with keys "product_page", "checkout", "success" — only entries
    with a configured URL are included. Non-fatal on any failure; returns {}.
    """
    result, *_ = await _load_subscriber_tagged_urls_with_product(
        db=db,
        org_id=org_id,
        attora_campaign_id=attora_campaign_id,
        subscriber_id=subscriber_id,
        attora_id=attora_id,
    )
    return result


async def _load_subscriber_tagged_urls_with_product(
    db: AsyncSession | None,
    org_id: uuid.UUID,
    attora_campaign_id: str | None,
    subscriber_id: str,
    attora_id: str | None = None,
) -> tuple[dict[str, str], str | None]:
    """
    Same as _load_subscriber_tagged_urls but also returns the campaign's
    linked product_id (so the prompt builder can filter the product catalog
    to just the campaign-attributed product).

    Returns: (urls_dict, product_id_str_or_None, utm_campaign_or_None, utm_source_or_None).
    """
    if db is None:
        return {}, None, None, None

    try:
        campaign = await fetch_managed_campaign_with_utm(db, org_id, attora_campaign_id)

        if campaign is None or campaign.utm is None:
            return {}, None, None, None

        # Prefer the pre-built *_utm_url fields (which already have funnel
        # utm_* baked in); fall back to the raw base URL only if the _utm_url
        # variant is missing. `build_dm_link` merges attora_* identity and
        # forces UTM medium to ``dm`` for outbound DM attribution.
        utm = campaign.utm
        urls: dict[str, str] = {}
        sub_view = DmSubscriberView.from_strings(subscriber_id, attora_id)

        def _stamp(base: str | None, tagged: str | None) -> str | None:
            source = tagged or base
            if not source:
                return None
            return build_dm_link(
                source,
                sub_view,
                utm.utm_campaign or "",
                utm.utm_source or "",
            )

        product_page = _stamp(utm.product_page_url, utm.product_page_utm_url)
        if product_page:
            urls["product_page"] = product_page

        checkout = _stamp(utm.checkout_url, utm.checkout_utm_url)
        if checkout:
            urls["checkout"] = checkout

        success = _stamp(utm.success_url, utm.success_utm_url)
        if success:
            urls["success"] = success

        product_id_str = (
            str(campaign.product_id) if campaign.product_id else None
        )
        utm_c, utm_s = dm_utm_strings_from_campaign(campaign)
        return (
            urls,
            product_id_str,
            utm_c,
            utm_s,
        )
    except Exception as e:
        logger.warning(
            "Failed to load per-subscriber UTM URLs for campaign %s: %s",
            attora_campaign_id,
            e,
        )
        return {}, None, None, None


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
        await _safe_rollback(db)
        return get_fallback_response(FallbackType.BUYING_TIME)
    except Exception as e:
        elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
        logger.error(
            f"Pipeline error after {elapsed_ms}ms for org={org_id}: {e}",
            exc_info=True,
        )
        await _safe_rollback(db)
        return get_fallback_response(FallbackType.ERROR)


async def _safe_rollback(db: AsyncSession | None) -> None:
    """Reset a session that may be mid-transaction after a pipeline abort.

    Why: asyncio.wait_for cancels an in-flight query without rolling back,
    leaving the connection poisoned ("Can't reconnect until invalid
    transaction is rolled back"). Any subsequent query on this session
    — including the endpoint code that runs after process_message returns
    the fallback — would then fail.
    """
    if db is None:
        return
    try:
        await db.rollback()
    except Exception as rollback_err:
        logger.warning(f"Session rollback after pipeline abort failed: {rollback_err}")


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

    # Kick off the classifier immediately — it's pure Haiku, no shared DB
    # session, so it overlaps with everything that follows (UTM lookup +
    # knowledge retrieval). Saves ~500-1500ms of serial latency.
    subscriber_brief = (
        f"Stage: {context.subscriber.buyer_stage}, "
        f"Messages: {context.subscriber.total_messages}"
    )
    classify_start = time.monotonic()
    classify_task = asyncio.create_task(
        classify_message(message, subscriber_brief)
    )

    # ── Step 2.1: Stamp per-subscriber UTM URLs ────────────────
    # So the AI can quote an attribution link scoped to THIS lead.
    # Stamps both attora_sub (ManyChat ID) and attora_id (Attora UUID).
    # Also returns the campaign's linked product_id so the prompt builder
    # can filter the product catalog to just that one product (prevents
    # cross-product hallucination).
    # Sequential with knowledge retrieval because both use the same
    # AsyncSession (not safe to share across concurrent tasks).
    (
        context.subscriber_tagged_urls,
        context.campaign_product_id,
        context.dm_utm_campaign,
        context.dm_utm_source,
    ) = await _load_subscriber_tagged_urls_with_product(
        db=db,
        org_id=org_id,
        attora_campaign_id=context.subscriber.attora_campaign_id,
        subscriber_id=subscriber_id,
        attora_id=context.subscriber.attora_id,
    )

    # ── Step 2.5: Retrieve knowledge (<1s via Haiku) ──────────
    if db is not None:
        try:
            step_start = time.monotonic()
            knowledge = await retrieve_knowledge(
                message=message,
                buyer_stage=context.subscriber.buyer_stage,
                ad_name=context.subscriber.hyros_origin_source,
                db=db,
            )
            context.retrieved_knowledge = knowledge
            logger.debug(
                f"Step 2.5 (knowledge): {int((time.monotonic() - step_start) * 1000)}ms "
                f"docs={len(knowledge)}"
            )
        except Exception as e:
            logger.error(f"Knowledge retrieval failed, continuing pipeline: {e}")

    # ── Step 3: Await classifier (overlapped with steps above) ─
    classification = await classify_task
    logger.debug(
        f"Step 3 (classify): {int((time.monotonic() - classify_start) * 1000)}ms "
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

    # Ensure we always include an actual campaign URL when the user asks to buy/get link.
    _inject_purchase_link_if_needed(
        ai_response=ai_response,
        message=message,
        intent=classification.intent,
        subscriber_tagged_urls=context.subscriber_tagged_urls,
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


def _inject_purchase_link_if_needed(
    ai_response: AIResponse,
    message: str,
    intent: IntentType,
    subscriber_tagged_urls: dict[str, str] | None,
) -> None:
    """Inject requested campaign URL (product/checkout/success) for buy/link intents."""
    text = (ai_response.response_text or "").strip()
    msg = (message or "").lower()

    urls = subscriber_tagged_urls or {}

    # Clinical/handoff escalation: if the AI's response already routed the lead
    # to a team call (booking link is in the text), do NOT append a product or
    # checkout URL alongside. The clinical/post-purchase escalation flow owns
    # the response — adding a purchase link dilutes the call CTA and confuses
    # leads being handed off (e.g. PCOS → call link should not be paired with
    # a Macro Method product URL).
    call_link = settings.warrior_babe_call_link
    if call_link and call_link in text:
        return

    # Past-tense purchase confirmations ("I just bought it", "got it", "I'm in").
    # Don't send any link — they already paid. Direct them to check their
    # email for access (the AI's text response handles that messaging).
    is_post_purchase_signal = any(hint in msg for hint in _POST_PURCHASE_HINTS)
    if is_post_purchase_signal:
        return

    # Already at purchase stage but current message has no purchase signal
    # (e.g. lead is now chatting post-purchase about something else).
    # Suppress all link injection — they already have access; spamming
    # checkout/product links creates re-purchase friction.
    if (ai_response.buyer_stage or "").lower() == "purchase":
        return

    # Skip if the customer is only asking about price/cost — no link needed.
    is_price_only = any(hint in msg for hint in _PRICE_ONLY_HINTS)
    if is_price_only:
        return

    is_buy_or_link_request = (
        intent == IntentType.PURCHASE_INTENT
        or any(hint in msg for hint in _PURCHASE_LINK_HINTS)
    )
    if not is_buy_or_link_request:
        return

    if not urls:
        return

    # Pick ONE URL based on message intent — never append all three.
    # Success URL is reserved for post-purchase signals (handled earlier);
    # at this point the lead is still in the buying funnel, so prefer
    # checkout > product_page. Never inject success here.
    requested_type = _infer_requested_link_type(msg)

    url_to_inject: str | None = None
    if requested_type == "checkout":
        url_to_inject = urls.get("checkout") or urls.get("product_page")
    elif requested_type == "product":
        url_to_inject = urls.get("product_page") or urls.get("checkout")
    elif requested_type == "success":
        # Pre-purchase ask for "success/confirmation" page — fall back to
        # the buy path since they haven't actually purchased yet.
        url_to_inject = urls.get("checkout") or urls.get("product_page")

    if not url_to_inject or url_to_inject in text:
        return

    if text:
        ai_response.response_text = f"{text}\n\n{url_to_inject}"
    else:
        ai_response.response_text = url_to_inject

    ai_response.conversion_ready = True


def _infer_requested_link_type(message_lower: str) -> str:
    """Infer which URL type the customer asked for: success, checkout, or product."""
    if any(h in message_lower for h in _SUCCESS_LINK_HINTS):
        return "success"
    if any(h in message_lower for h in _CHECKOUT_LINK_HINTS):
        return "checkout"
    if any(h in message_lower for h in _PRODUCT_LINK_HINTS):
        return "product"
    return "checkout"


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
        # Only use the canned greeting for the VERY FIRST message.
        # Mid-conversation short replies like "Maggie" or "Yes, Nikkiey!"
        # can be misclassified as greetings — send those to Sonnet instead.
        if context.subscriber.total_messages <= 1 and not context.history:
            return get_fallback_response(
                FallbackType.GREETING,
                custom_greeting=org_config.ai_config.greeting_message,
            )
        return None  # Let Sonnet handle with full conversation context.

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
