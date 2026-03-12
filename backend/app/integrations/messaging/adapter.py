"""
Attora — Abstract Messaging Adapter

Defines the interface for messaging platform integrations. All platform
adapters (ManyChat, etc.) must implement this interface.
"""

from __future__ import annotations

import abc
from typing import Any


class MessagingAdapter(abc.ABC):
    """
    Abstract interface for messaging platform adapters.

    All platform-specific implementations must subclass this and implement
    the required methods. Operations are async to support non-blocking I/O.
    """

    @abc.abstractmethod
    async def send_message(
        self,
        subscriber_id: str,
        text: str,
        quick_replies: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Send a text message to a subscriber.

        Args:
            subscriber_id: Platform-specific subscriber ID.
            text: Message text to send.
            quick_replies: Optional list of quick reply button captions.

        Returns:
            Platform-specific response data.
        """
        ...

    @abc.abstractmethod
    async def get_subscriber_info(
        self,
        subscriber_id: str,
    ) -> dict[str, Any]:
        """
        Get subscriber profile information from the platform.

        Args:
            subscriber_id: Platform-specific subscriber ID.

        Returns:
            Dict with subscriber profile data.
        """
        ...

    @abc.abstractmethod
    async def set_custom_fields(
        self,
        subscriber_id: str,
        fields: dict[str, str],
    ) -> dict[str, Any]:
        """
        Set custom field values on a subscriber.

        Args:
            subscriber_id: Platform-specific subscriber ID.
            fields: Dict of field_name -> value pairs.

        Returns:
            Platform-specific response data.
        """
        ...

    @abc.abstractmethod
    async def trigger_flow(
        self,
        subscriber_id: str,
        flow_ns: str,
    ) -> dict[str, Any]:
        """
        Trigger a flow/automation for a subscriber.

        Args:
            subscriber_id: Platform-specific subscriber ID.
            flow_ns: Platform-specific flow namespace/identifier.

        Returns:
            Platform-specific response data.
        """
        ...
