"""
Attora — Messaging Integrations

Abstract messaging adapter interface and platform implementations.
"""

from app.integrations.messaging.adapter import MessagingAdapter
from app.integrations.messaging.manychat import ManyChatAdapter

__all__ = ["MessagingAdapter", "ManyChatAdapter"]
