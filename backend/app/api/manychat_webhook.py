"""
Attora — ManyChat Webhook Endpoint

POST /api/manychat/webhook — THE critical path.

ManyChat's External Request action calls this endpoint with subscriber data
and expects a v2 JSON response within 10 seconds. Authentication is via
X-Attora-Key header (NOT JWT), validated against organizations.attora_api_key.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
import json

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import Organization
from app.models.manychat_event import ManyChatEvent
from app.redis import get_redis_pool
from app.schemas.manychat import ManyChatWebhookRequest, ManyChatWebhookResponse
from app.security.encryption import decrypt_value
from app.services.ai_engine import process_message
from app.services.fallback import FallbackType, get_fallback_manychat_response

logger = logging.getLogger(__name__)

router = APIRouter()

# Total endpoint time budget (ManyChat requires response within 10s)
_ENDPOINT_TIMEOUT_SECONDS = 9.5  # Leave 500ms buffer for serialization


async def _authenticate_api_key(
    x_attora_key: str = Header(..., description="Attora API key for webhook auth"),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """
    Authenticate the webhook request via X-Attora-Key header.

    Decrypts stored attora_api_key values and compares against the
    provided key. Returns the org_id on success.

    NOTE: For production scale, consider caching the key->org_id mapping
    in Redis to avoid per-request DB lookups + decryption.
    """
    if not x_attora_key or len(x_attora_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Try Redis cache first for key->org_id mapping
    org_id = await _check_key_cache(x_attora_key)
    if org_id:
        return org_id

    # Fall back to DB lookup
    result = await db.execute(
        select(Organization.id, Organization.attora_api_key)
        .where(Organization.attora_api_key.isnot(None))
    )
    rows = result.all()

    for row in rows:
        try:
            decrypted_key = decrypt_value(row.attora_api_key)
            if decrypted_key == x_attora_key:
                # Cache the mapping for future requests
                await _cache_key_mapping(x_attora_key, row.id)
                return row.id
        except Exception:
            # Skip rows with decryption errors
            continue

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def _check_key_cache(api_key: str) -> uuid.UUID | None:
    """Check Redis cache for API key -> org_id mapping."""
    try:
        redis = get_redis_pool()
        import hashlib
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        cache_key = f"apikey:{key_hash}"
        cached_org_id = await redis.get(cache_key)
        if cached_org_id:
            return uuid.UUID(cached_org_id)
    except Exception:
        pass
    return None


async def _cache_key_mapping(api_key: str, org_id: uuid.UUID) -> None:
    """Cache API key -> org_id mapping in Redis (1 hour TTL)."""
    try:
        redis = get_redis_pool()
        import hashlib
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        cache_key = f"apikey:{key_hash}"
        await redis.setex(cache_key, 3600, str(org_id))
    except Exception:
        pass


@router.post(
    "/webhook",
    response_model=ManyChatWebhookResponse,
    summary="ManyChat External Request Webhook",
    description=(
        "Receives subscriber data from ManyChat External Request, "
        "processes through the AI engine, and returns a ManyChat v2 response."
    ),
)
async def manychat_webhook(
    request: ManyChatWebhookRequest,
    org_id: uuid.UUID = Depends(_authenticate_api_key),
    db: AsyncSession = Depends(get_db),
) -> ManyChatWebhookResponse:
    """
    ManyChat webhook endpoint — the critical path.

    Flow:
    1. Authenticate via X-Attora-Key header
    2. Parse ManyChat payload
    3. Call AI engine pipeline
    4. Return ManyChat v2 response format

    Total time budget: 10 seconds (with 500ms buffer).
    """
    # Diagnostic: log raw incoming payload early to diagnose missing workflows
    try:
        payload = request.model_dump(exclude_none=False)
        logger.info("[WEBHOOK] Received payload: %s", json.dumps(payload, indent=2))
    except Exception:
        logger.exception("[WEBHOOK] Failed to serialize webhook payload")

    logger.info(
        "[WEBHOOK] channel=%s flow_id=%s subscriber_id=%s",
        request.channel,
        request.flow_id,
        getattr(request.subscriber, "id", None),
    )

    # If ManyChat provided an attora_campaign_id in top-level fields or custom_fields,
    # log it and attempt a diagnostic lookup in the DB (non-fatal)
    try:
        # custom_fields extraction happens below; peek at top-level subscriber fields too
        top_attora = None
        try:
            top_attora = (request.subscriber.custom_fields or {}).get("attora_campaign_id") if request.subscriber and getattr(request.subscriber, 'custom_fields', None) else None
        except Exception:
            top_attora = None
        # We'll inspect again after building custom_fields, but log this quick snapshot now
        if top_attora:
            logger.info("[WEBHOOK] attora_campaign_id (top-level) received: %s", top_attora)
    except Exception:
        logger.exception("[WEBHOOK] Error while inspecting attora_campaign_id")

    start_time = time.monotonic()

    subscriber_id = request.subscriber.id
    message = request.last_input_text
    channel = request.channel
    flow_id = (request.flow_id or "").strip()

    # Extract custom fields as dict
    custom_fields: dict = {}
    if request.subscriber.custom_fields:
        cf = request.subscriber.custom_fields
        custom_fields = cf.model_dump(exclude_none=True)

    # Always capture identity from the subscriber object — ManyChat sends
    # these as top-level subscriber fields regardless of whether custom_fields
    # is present. Extracting them inside the custom_fields block caused them
    # to be silently dropped whenever custom_fields was null.
    if request.subscriber.first_name:
        custom_fields["first_name"] = request.subscriber.first_name
    if request.subscriber.last_name:
        custom_fields["last_name"] = request.subscriber.last_name
    if request.subscriber.phone:
        custom_fields["phone"] = request.subscriber.phone
    if request.subscriber.email:
        custom_fields["email"] = request.subscriber.email

    # Diagnostic: log attora_campaign_id from custom_fields and attempt DB lookup
    try:
        attora_campaign_id = custom_fields.get("attora_campaign_id")
        logger.info("[WEBHOOK] attora_campaign_id received: %s", attora_campaign_id)
        if attora_campaign_id:
            try:
                camp_uuid = uuid.UUID(attora_campaign_id)
            except Exception:
                camp_uuid = None
            if camp_uuid:
                try:
                    from sqlalchemy import select
                    from app.models.campaign import AdCampaign

                    result = await db.execute(select(AdCampaign).where(AdCampaign.id == camp_uuid))
                    campaign = result.scalar_one_or_none()
                    logger.info("[WEBHOOK] campaign lookup result: %s", getattr(campaign, "name", None) if campaign else None)
                except Exception:
                    logger.exception("[WEBHOOK] campaign lookup failed for id: %s", attora_campaign_id)
    except Exception:
        logger.exception("[WEBHOOK] Error while logging attora_campaign_id")

    # Log attribution fields so we can trace organic vs paid and debug 14-vs-8 gaps.
    _post_id  = custom_fields.get("post_id")  or "(none)"
    _ad_id    = custom_fields.get("ad_id")    or "(none)"
    _ctwa     = custom_fields.get("ctwa_clid") or "(none)"
    logger.info(
        "Webhook received: org=%s subscriber=%s channel=%s "
        "post_id=%r ad_id=%r ctwa_clid=%r msg_len=%d",
        org_id, subscriber_id, channel,
        _post_id, _ad_id, _ctwa, len(message),
    )

    event_type_raw = (request.event_type or "").strip().lower()
    is_click_event = bool(
        request.clicked is True
        or request.button_clicked is True
        or event_type_raw in {"clicked", "click", "button_clicked", "button_click"}
    )

    # Get Redis client (non-fatal if unavailable)
    redis_client = None
    try:
        redis_client = get_redis_pool()
    except RuntimeError:
        logger.warning("Redis unavailable for webhook request")

    # Process through AI engine with timeout
    try:
        ai_response = await asyncio.wait_for(
            process_message(
                org_id=org_id,
                subscriber_id=subscriber_id,
                message=message,
                channel=channel,
                custom_fields=custom_fields,
                db=db,
                redis_client=redis_client,
            ),
            timeout=_ENDPOINT_TIMEOUT_SECONDS,
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "Webhook response in %dms: org=%s subscriber=%s model=%s stage=%s handoff=%s",
            elapsed_ms, org_id, subscriber_id,
            ai_response.model_used, ai_response.buyer_stage, ai_response.needs_human_handoff,
        )
        webhook_response = ManyChatWebhookResponse.from_ai_response(
            response_text=ai_response.response_text,
            buyer_stage=ai_response.buyer_stage,
            quick_replies=ai_response.suggested_quick_replies,
            custom_field_updates=ai_response.custom_field_updates,
        )
    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.warning(
            "Webhook timeout after %dms: org=%s subscriber=%s",
            elapsed_ms, org_id, subscriber_id,
        )
        webhook_response = get_fallback_manychat_response(FallbackType.BUYING_TIME)
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            "Webhook error after %dms: org=%s error=%s",
            elapsed_ms, org_id, e,
            exc_info=True,
        )
        webhook_response = get_fallback_manychat_response(FallbackType.ERROR)

    # Persist the webhook event AFTER process_message so it is never wiped by
    # _safe_rollback: that helper calls db.rollback() on timeout/error paths
    # (to unpoison the connection), which would silently erase any ManyChatEvent
    # staged before the pipeline ran.  After process_message returns the session
    # is either committed-clean (success) or rolled-back-clean (fallback) — safe
    # to add new rows in both cases.
    if flow_id:
        try:
            # Normalise channel: ManyChat sends "facebook" for Messenger flows;
            # map it to "messenger" so it matches preferred_flow_ids_by_channel.
            raw_ch = (channel or "messenger").lower()
            norm_ch = "messenger" if raw_ch == "facebook" else raw_ch

            logger.info(
                "Persisting manychat event: org=%s subscriber=%s flow_id=%s channel=%s click=%s",
                org_id, subscriber_id, flow_id, norm_ch, is_click_event,
            )
            db.add(
                ManyChatEvent(
                    org_id=org_id,
                    manychat_subscriber_id=subscriber_id,
                    flow_id=flow_id,
                    event_type="sent",
                    channel=norm_ch,
                )
            )
            if is_click_event:
                db.add(
                    ManyChatEvent(
                        org_id=org_id,
                        manychat_subscriber_id=subscriber_id,
                        flow_id=flow_id,
                        event_type="clicked",
                        channel=norm_ch,
                    )
                )
            await db.flush()
            logger.info(
                "Manychat event flushed: org=%s subscriber=%s flow_id=%s",
                org_id, subscriber_id, flow_id,
            )
        except Exception:
            logger.exception(
                "Failed to persist manychat webhook event: org=%s subscriber=%s flow_id=%s",
                org_id, subscriber_id, flow_id,
            )
            # If the flush poisoned the session (e.g. after a prior _safe_rollback left
            # the connection in a broken state), roll back so get_db's commit succeeds
            # and the fallback response is delivered instead of a 500.
            try:
                await db.rollback()
            except Exception:
                pass

    return webhook_response
