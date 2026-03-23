"""
Tests for subscriber/leads schema field mapping.

Verifies that the backend SubscriberListItem and SubscriberDetail schemas
return the correct field names that the frontend expects. This was a bug
where the frontend used different field names (name, first_contact_at,
conversation_count) than the backend (first_name/last_name, first_message_at,
total_messages).
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.schemas.subscriber import SubscriberListItem, SubscriberDetail, SubscriberConversationSummary


class TestSubscriberListItem:
    """Verify SubscriberListItem schema matches frontend expectations."""

    def _make_item(self, **overrides) -> SubscriberListItem:
        defaults = {
            "id": uuid.uuid4(),
            "first_name": "Jane",
            "last_name": "Smith",
            "channel": "instagram",
            "buyer_stage": "awareness",
            "is_converted": False,
            "conversion_value": None,
            "total_messages": 5,
            "first_message_at": datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc),
            "last_message_at": datetime(2026, 3, 21, 14, 30, 0, tzinfo=timezone.utc),
            "created_at": datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc),
        }
        defaults.update(overrides)
        return SubscriberListItem(**defaults)

    def test_has_first_name_and_last_name(self):
        """Backend sends first_name/last_name, not a combined 'name' field."""
        item = self._make_item(first_name="Jane", last_name="Smith")
        data = item.model_dump()
        assert "first_name" in data
        assert "last_name" in data
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Smith"
        # Must NOT have old 'name' field
        assert "name" not in data

    def test_has_first_message_at_not_first_contact_at(self):
        """Backend sends first_message_at, not first_contact_at."""
        item = self._make_item()
        data = item.model_dump()
        assert "first_message_at" in data
        assert "first_contact_at" not in data

    def test_has_last_message_at_not_last_contact_at(self):
        """Backend sends last_message_at, not last_contact_at."""
        item = self._make_item()
        data = item.model_dump()
        assert "last_message_at" in data
        assert "last_contact_at" not in data

    def test_has_total_messages_not_conversation_count(self):
        """Backend sends total_messages, not conversation_count."""
        item = self._make_item(total_messages=12)
        data = item.model_dump()
        assert "total_messages" in data
        assert data["total_messages"] == 12
        assert "conversation_count" not in data

    def test_does_not_have_external_id(self):
        """Backend does not send external_id in list items."""
        item = self._make_item()
        data = item.model_dump()
        assert "external_id" not in data

    def test_nullable_name_fields(self):
        """Name fields can be null (ManyChat may not provide them)."""
        item = self._make_item(first_name=None, last_name=None)
        data = item.model_dump()
        assert data["first_name"] is None
        assert data["last_name"] is None

    def test_nullable_date_fields(self):
        """Date fields can be null for new subscribers with no messages yet."""
        item = self._make_item(first_message_at=None, last_message_at=None)
        data = item.model_dump()
        assert data["first_message_at"] is None
        assert data["last_message_at"] is None

    def test_serializes_to_json_with_correct_fields(self):
        """JSON output has exactly the expected fields."""
        item = self._make_item()
        data = item.model_dump(mode="json")
        expected_fields = {
            "id", "first_name", "last_name", "channel", "buyer_stage",
            "is_converted", "conversion_value", "total_messages",
            "first_message_at", "last_message_at", "created_at",
        }
        assert set(data.keys()) == expected_fields


class TestSubscriberDetail:
    """Verify SubscriberDetail schema matches frontend expectations."""

    def _make_detail(self, **overrides) -> SubscriberDetail:
        defaults = {
            "id": uuid.uuid4(),
            "manychat_subscriber_id": "mc-12345",
            "channel": "messenger",
            "first_name": "John",
            "last_name": "Doe",
            "phone": None,
            "email": None,
            "buyer_stage": "consideration",
            "interests": ["glp-1", "weight-loss"],
            "objections_raised": ["price"],
            "conversation_summary": "Interested in GLP-1 program.",
            "is_converted": False,
            "conversion_value": None,
            "converted_at": None,
            "first_message_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
            "last_message_at": datetime(2026, 3, 21, tzinfo=timezone.utc),
            "total_messages": 8,
            "created_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 3, 21, tzinfo=timezone.utc),
            "conversations": [],
        }
        defaults.update(overrides)
        return SubscriberDetail(**defaults)

    def test_has_manychat_subscriber_id_not_external_id(self):
        """Backend sends manychat_subscriber_id, not external_id."""
        detail = self._make_detail()
        data = detail.model_dump()
        assert "manychat_subscriber_id" in data
        assert "external_id" not in data

    def test_has_objections_raised_not_objections(self):
        """Backend sends objections_raised, not objections."""
        detail = self._make_detail(objections_raised=["price", "timing"])
        data = detail.model_dump()
        assert "objections_raised" in data
        assert "objections" not in data

    def test_has_conversation_summary(self):
        """Backend sends conversation_summary field."""
        detail = self._make_detail(conversation_summary="Interested in GLP-1.")
        data = detail.model_dump()
        assert "conversation_summary" in data
        assert data["conversation_summary"] == "Interested in GLP-1."

    def test_does_not_have_custom_fields(self):
        """Backend does not send a generic custom_fields dict."""
        detail = self._make_detail()
        data = detail.model_dump()
        assert "custom_fields" not in data

    def test_conversations_have_correct_fields(self):
        """Embedded conversations use started_at/last_activity_at, not created_at/last_message_at."""
        conv = SubscriberConversationSummary(
            id=uuid.uuid4(),
            channel="instagram",
            status="active",
            message_count=3,
            started_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            last_activity_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
        )
        data = conv.model_dump()
        assert "started_at" in data
        assert "last_activity_at" in data
        assert "created_at" not in data
        assert "last_message_at" not in data
