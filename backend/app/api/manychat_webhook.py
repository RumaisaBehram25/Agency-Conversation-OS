"""
Attora — ManyChat Webhook Endpoint

POST /api/manychat/webhook — THE critical path.

ManyChat's External Request action calls this endpoint with subscriber data
and expects a v2 JSON response within 10 seconds. Authentication is via
X-Attora-Key header (NOT JWT), validated against organizations.attora_api_key.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import Organization
from app.redis import get_redis_pool
from app.schemas.manychat import ManyChatWebhookRequest, ManyChatWebhookResponse
from app.security.encryption import decrypt_value
from app.services.ai_engine import generate_ai_response
from app.services.fallback import FallbackType, get_fallback_manychat_response

logger = logging.getLogger(__name__)

router = APIRouter()

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
    start_time = time.monotonic()

    logger.info("🔔 Incoming ManyChat webhook: %s", request.model_dump())

    subscriber_id = request.subscriber.id

    message = (request.last_input_text or "").strip()
    channel = request.channel

    if not message:
        logger.warning(
            "⚠️ Empty last_input_text received: org=%s subscriber=%s channel=%s",
            org_id,
            subscriber_id,
            channel,
        )
        return ManyChatWebhookResponse.from_ai_response(
            response_text="Please send a message so I can help you 🙂",
            buyer_stage=None,
            quick_replies=None,
            custom_field_updates=None,
        )

    # Extract custom fields as dict
    custom_fields: dict = {}
    if request.subscriber.custom_fields:
        cf = request.subscriber.custom_fields
        custom_fields = cf.model_dump(exclude_none=True)
        # Also include subscriber identity info
        if request.subscriber.first_name:
            custom_fields["first_name"] = request.subscriber.first_name
        if request.subscriber.last_name:
            custom_fields["last_name"] = request.subscriber.last_name
        if request.subscriber.phone:
            custom_fields["phone"] = request.subscriber.phone
        if request.subscriber.email:
            custom_fields["email"] = request.subscriber.email

    logger.info(
        f"Webhook received: org={org_id}, subscriber={subscriber_id}, "
        f"channel={channel}, message_length={len(message)}"
    )

    # Get Redis client (non-fatal if unavailable)
    redis_client = None
    try:
        redis_client = get_redis_pool()
    except RuntimeError:
        logger.warning("Redis unavailable for webhook request")

    # Process through AI pipeline wrapper
    try:
        ai_response = await generate_ai_response(
            text=message,
            subscriber_id=subscriber_id,
            org_id=org_id,
            channel=channel,
            custom_fields=custom_fields,
            db=db,
            redis_client=redis_client,
        )
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            f"Webhook error after {elapsed_ms}ms for org={org_id}: {e}",
            exc_info=True,
        )
        return get_fallback_manychat_response(FallbackType.ERROR)

    # Build ManyChat v2 response
    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    logger.info(
        f"Webhook response in {elapsed_ms}ms: org={org_id}, "
        f"subscriber={subscriber_id}, model={ai_response.model_used}, "
        f"stage={ai_response.buyer_stage}, handoff={ai_response.needs_human_handoff}"
    )

    return ManyChatWebhookResponse.from_ai_response(
        response_text=ai_response.response_text,
        buyer_stage=ai_response.buyer_stage,
        quick_replies=ai_response.suggested_quick_replies,
        custom_field_updates=ai_response.custom_field_updates,
    )
