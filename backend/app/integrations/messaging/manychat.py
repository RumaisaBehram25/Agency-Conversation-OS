"""
Attora — ManyChat Messaging Adapter

Implementation of the MessagingAdapter interface for ManyChat.
Uses httpx async HTTP client to interact with the ManyChat API v2.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.messaging.adapter import MessagingAdapter

logger = logging.getLogger(__name__)

# ManyChat API configuration
_MANYCHAT_API_BASE = "https://api.manychat.com/fb"
_MANYCHAT_INSTAGRAM_API_BASE = "https://api.manychat.com/instagram"
_DEFAULT_TIMEOUT = 10.0  # seconds


class ManyChatAdapter(MessagingAdapter):
    """
    ManyChat messaging adapter.

    Provides methods to send messages, get subscriber info, set custom
    fields, and trigger flows via the ManyChat API.

    Args:
        api_key: ManyChat API key (Bearer token).
        timeout: HTTP request timeout in seconds.
    """

    def __init__(self, api_key: str, timeout: float = _DEFAULT_TIMEOUT):
        self._api_key = api_key
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def send_message(
        self,
        subscriber_id: str,
        text: str,
        quick_replies: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send a text message to a ManyChat subscriber."""
        payload: dict[str, Any] = {
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    "messages": [
                        {"type": "text", "text": text}
                    ],
                },
            },
        }

        if quick_replies:
            payload["data"]["content"]["quick_replies"] = [
                {"type": "node", "caption": caption}
                for caption in quick_replies[:3]  # ManyChat max 3
            ]

        return await self._post("/sending/sendContent", payload)

    async def send_instagram_message(
        self,
        subscriber_id: str,
        text: str,
    ) -> dict[str, Any]:
        """Send a text message to an Instagram subscriber via ManyChat."""
        payload: dict[str, Any] = {
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    "messages": [
                        {"type": "text", "text": text}
                    ],
                },
            },
        }
        return await self._post_instagram("/sending/sendContent", payload)

    async def get_subscriber_info(
        self,
        subscriber_id: str,
    ) -> dict[str, Any]:
        """Get subscriber info from ManyChat."""
        return await self._get(
            "/subscriber/getInfo",
            params={"subscriber_id": subscriber_id},
        )

    async def set_custom_fields(
        self,
        subscriber_id: str,
        fields: dict[str, str],
    ) -> dict[str, Any]:
        """Set custom fields on a ManyChat subscriber."""
        # ManyChat expects an array of field objects
        field_objects = [
            {"field_name": name, "field_value": value}
            for name, value in fields.items()
        ]

        payload = {
            "subscriber_id": subscriber_id,
            "fields": field_objects,
        }

        return await self._post("/subscriber/setCustomFields", payload)

    async def trigger_flow(
        self,
        subscriber_id: str,
        flow_ns: str,
    ) -> dict[str, Any]:
        """Trigger a ManyChat flow for a subscriber."""
        payload = {
            "subscriber_id": subscriber_id,
            "flow_ns": flow_ns,
        }

        return await self._post("/sending/sendFlow", payload)

    async def _post(self, endpoint: str, payload: dict) -> dict[str, Any]:
        """Make a POST request to the ManyChat API."""
        url = f"{_MANYCHAT_API_BASE}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.error(f"ManyChat API timeout: POST {endpoint}")
            raise

        except httpx.HTTPStatusError as e:
            logger.error(
                f"ManyChat API error: POST {endpoint} -> {e.response.status_code}: "
                f"{e.response.text[:500]}"
            )
            raise

        except Exception as e:
            logger.error(f"ManyChat API request failed: POST {endpoint}: {e}")
            raise

    async def _post_instagram(self, endpoint: str, payload: dict) -> dict[str, Any]:
        """POST to ManyChat Instagram API (e.g. /instagram/sending/sendContent)."""
        url = f"{_MANYCHAT_INSTAGRAM_API_BASE}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.error(f"ManyChat Instagram API timeout: POST {endpoint}")
            raise

        except httpx.HTTPStatusError as e:
            logger.error(
                f"ManyChat Instagram API error: POST {endpoint} -> {e.response.status_code}: "
                f"{e.response.text[:500]}"
            )
            raise

        except Exception as e:
            logger.error(f"ManyChat Instagram API request failed: POST {endpoint}: {e}")
            raise

    async def _get(
        self, endpoint: str, params: dict | None = None
    ) -> dict[str, Any]:
        """Make a GET request to the ManyChat API."""
        url = f"{_MANYCHAT_API_BASE}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.error(f"ManyChat API timeout: GET {endpoint}")
            raise

        except httpx.HTTPStatusError as e:
            logger.error(
                f"ManyChat API error: GET {endpoint} -> {e.response.status_code}: "
                f"{e.response.text[:500]}"
            )
            raise

        except Exception as e:
            logger.error(f"ManyChat API request failed: GET {endpoint}: {e}")
            raise
