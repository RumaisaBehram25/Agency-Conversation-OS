"""
Attora — Meta Conversions API (CAPI) Client

Fires conversion events to the Meta Graph API for ad attribution and
optimization. Supports Lead, Purchase, and InitiateCheckout events.

All operations are async, fire-and-forget with error logging.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Meta Graph API configuration
_GRAPH_API_VERSION = "v21.0"
_GRAPH_API_BASE = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"
_DEFAULT_TIMEOUT = 10.0  # seconds

# Supported event names
SUPPORTED_EVENTS = {"LeadSubmitted", "Purchase", "InitiateCheckout"}

# Channel to messaging_channel mapping
_CHANNEL_MAP = {
    "whatsapp": "whatsapp",
    "messenger": "messenger",
    "instagram": "instagram",
}


async def fire_conversion_event(
    pixel_id: str,
    access_token: str,
    event_name: str,
    subscriber_id: str,
    channel: str = "messenger",
    ctwa_clid: str | None = None,
    value: float | None = None,
    currency: str = "USD",
    custom_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Fire a conversion event to Meta Conversions API.

    Args:
        pixel_id: Meta Pixel ID.
        access_token: Meta CAPI access token.
        event_name: Event name (Lead, Purchase, InitiateCheckout).
        subscriber_id: ManyChat subscriber ID (used for external_id hash).
        channel: Messaging channel (whatsapp, messenger, instagram).
        ctwa_clid: Click-to-WhatsApp click ID for attribution.
        value: Conversion value amount.
        currency: Currency code (default USD).
        custom_data: Additional custom data fields.

    Returns:
        API response dict or None on failure.
    """
    if event_name not in SUPPORTED_EVENTS:
        logger.warning(f"Unsupported CAPI event: {event_name}")
        return None

    # Build event data
    event_id = str(uuid.uuid4())
    event_time = int(time.time())

    # Hash subscriber ID for user_data (Meta requires hashed data)
    hashed_external_id = hashlib.sha256(
        subscriber_id.encode("utf-8")
    ).hexdigest()

    user_data: dict[str, Any] = {
        "external_id": [hashed_external_id],
    }

    # Add click ID for attribution
    if ctwa_clid:
        user_data["ctwa_clid"] = ctwa_clid

    # Build event
    event: dict[str, Any] = {
        "event_name": event_name,
        "event_time": event_time,
        "event_id": event_id,
        "action_source": "business_messaging",
        "messaging_channel": _CHANNEL_MAP.get(channel.lower(), "messenger"),
        "user_data": user_data,
    }

    # Add value data for Purchase/InitiateCheckout
    if value is not None:
        event["custom_data"] = {
            "value": value,
            "currency": currency,
        }
    elif custom_data:
        event["custom_data"] = custom_data

    # Build request payload
    payload = {
        "data": [event],
    }

    # Send to Meta
    url = f"{_GRAPH_API_BASE}/{pixel_id}/events"
    params = {"access_token": access_token}

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.post(
                url,
                params=params,
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            events_received = result.get("events_received", 0)
            logger.info(
                f"CAPI {event_name} event sent: pixel={pixel_id}, "
                f"event_id={event_id}, events_received={events_received}"
            )
            return result

    except httpx.TimeoutException:
        logger.error(
            f"CAPI timeout: {event_name} event to pixel {pixel_id}"
        )
        return None

    except httpx.HTTPStatusError as e:
        logger.error(
            f"CAPI HTTP error: {event_name} event to pixel {pixel_id} -> "
            f"{e.response.status_code}: {e.response.text[:500]}"
        )
        return None

    except Exception as e:
        logger.error(
            f"CAPI request failed: {event_name} event to pixel {pixel_id}: {e}"
        )
        return None


async def fire_lead_event(
    pixel_id: str,
    access_token: str,
    subscriber_id: str,
    channel: str = "messenger",
    ctwa_clid: str | None = None,
) -> dict[str, Any] | None:
    """Convenience wrapper for Lead events."""
    return await fire_conversion_event(
        pixel_id=pixel_id,
        access_token=access_token,
        event_name="LeadSubmitted",
        subscriber_id=subscriber_id,
        channel=channel,
        ctwa_clid=ctwa_clid,
    )


async def fire_purchase_event(
    pixel_id: str,
    access_token: str,
    subscriber_id: str,
    value: float,
    currency: str = "USD",
    channel: str = "messenger",
    ctwa_clid: str | None = None,
) -> dict[str, Any] | None:
    """Convenience wrapper for Purchase events."""
    return await fire_conversion_event(
        pixel_id=pixel_id,
        access_token=access_token,
        event_name="Purchase",
        subscriber_id=subscriber_id,
        channel=channel,
        ctwa_clid=ctwa_clid,
        value=value,
        currency=currency,
    )


async def fire_initiate_checkout_event(
    pixel_id: str,
    access_token: str,
    subscriber_id: str,
    value: float | None = None,
    currency: str = "USD",
    channel: str = "messenger",
    ctwa_clid: str | None = None,
) -> dict[str, Any] | None:
    """Convenience wrapper for InitiateCheckout events."""
    return await fire_conversion_event(
        pixel_id=pixel_id,
        access_token=access_token,
        event_name="InitiateCheckout",
        subscriber_id=subscriber_id,
        channel=channel,
        ctwa_clid=ctwa_clid,
        value=value,
        currency=currency,
    )
