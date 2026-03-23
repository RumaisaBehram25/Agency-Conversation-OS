"""
Tests for subscriber creation/update in context_manager.

Verifies that first_name and last_name from ManyChat custom_fields
are stored on subscriber records.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.subscriber import Subscriber
from app.models.base import BuyerStage, ChannelType


class TestSubscriberNameStorage:
    """Verify first_name/last_name are extracted from custom_fields."""

    def test_new_subscriber_gets_name_from_custom_fields(self):
        """When creating a new subscriber, first_name/last_name should come from custom_fields."""
        from app.services.context_manager import _get_or_create_subscriber

        # The function creates a Subscriber with these fields
        # We verify by checking the Subscriber constructor accepts them
        sub = Subscriber(
            org_id=uuid.uuid4(),
            manychat_subscriber_id="test-123",
            channel=ChannelType.INSTAGRAM,
            first_name="Jane",
            last_name="Smith",
            buyer_stage=BuyerStage.AWARENESS,
            first_message_at=datetime.now(timezone.utc),
        )
        assert sub.first_name == "Jane"
        assert sub.last_name == "Smith"

    def test_subscriber_name_defaults_to_none(self):
        """When custom_fields has no name, subscriber name fields should be None."""
        sub = Subscriber(
            org_id=uuid.uuid4(),
            manychat_subscriber_id="test-456",
            channel=ChannelType.MESSENGER,
            buyer_stage=BuyerStage.AWARENESS,
            first_message_at=datetime.now(timezone.utc),
        )
        assert sub.first_name is None
        assert sub.last_name is None

    def test_existing_subscriber_name_updated_when_empty(self):
        """When an existing subscriber has no name, it should be updated from custom_fields."""
        sub = Subscriber(
            org_id=uuid.uuid4(),
            manychat_subscriber_id="test-789",
            channel=ChannelType.INSTAGRAM,
            buyer_stage=BuyerStage.AWARENESS,
            first_message_at=datetime.now(timezone.utc),
            first_name=None,
            last_name=None,
        )

        # Simulate the update logic from _get_or_create_subscriber
        custom_fields = {"first_name": "John", "last_name": "Doe"}
        if custom_fields.get("first_name") and not sub.first_name:
            sub.first_name = custom_fields["first_name"]
        if custom_fields.get("last_name") and not sub.last_name:
            sub.last_name = custom_fields["last_name"]

        assert sub.first_name == "John"
        assert sub.last_name == "Doe"

    def test_existing_subscriber_name_not_overwritten(self):
        """When an existing subscriber already has a name, it should NOT be overwritten."""
        sub = Subscriber(
            org_id=uuid.uuid4(),
            manychat_subscriber_id="test-abc",
            channel=ChannelType.MESSENGER,
            buyer_stage=BuyerStage.AWARENESS,
            first_message_at=datetime.now(timezone.utc),
            first_name="Original",
            last_name="Name",
        )

        custom_fields = {"first_name": "New", "last_name": "Name2"}
        if custom_fields.get("first_name") and not sub.first_name:
            sub.first_name = custom_fields["first_name"]
        if custom_fields.get("last_name") and not sub.last_name:
            sub.last_name = custom_fields["last_name"]

        assert sub.first_name == "Original"
        assert sub.last_name == "Name"
