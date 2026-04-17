from datetime import date, datetime, timezone

from app.jobs.olap_exports import _build_ai_usage_event_agg_records, _build_archived_message_agg_records


def test_build_ai_usage_event_agg_records_rolls_up_by_conversation_and_day():
    timestamp = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)

    rows = _build_ai_usage_event_agg_records(
        [
            {
                "org_id": "org-a",
                "conversation_id": "conv-1",
                "event_date": date(2026, 4, 1),
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read_tokens": 3,
                "cache_creation_tokens": 1,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            {
                "org_id": "org-a",
                "conversation_id": "conv-1",
                "event_date": date(2026, 4, 1),
                "input_tokens": 7,
                "output_tokens": 2,
                "cache_read_tokens": 1,
                "cache_creation_tokens": 0,
                "created_at": timestamp.replace(hour=13),
                "updated_at": timestamp.replace(hour=13),
            },
        ]
    )

    assert rows == [
        {
            "org_id": "org-a",
            "conversation_id": "conv-1",
            "event_date": date(2026, 4, 1),
            "event_count": 2,
            "input_tokens": 17,
            "output_tokens": 7,
            "cache_read_tokens": 4,
            "cache_creation_tokens": 1,
            "first_event_at": timestamp,
            "last_event_at": timestamp.replace(hour=13),
            "created_at": timestamp,
            "updated_at": timestamp.replace(hour=13),
        }
    ]


def test_build_archived_message_agg_records_rolls_up_by_conversation_and_day():
    timestamp = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)

    rows = _build_archived_message_agg_records(
        [
            {
                "org_id": "org-a",
                "conversation_id": "conv-1",
                "event_date": date(2026, 4, 1),
                "sender": "user",
                "ai_tokens_used": None,
                "ai_response_time_ms": None,
                "conversation_channel": "messenger",
                "conversation_status": "open",
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            {
                "org_id": "org-a",
                "conversation_id": "conv-1",
                "event_date": date(2026, 4, 1),
                "sender": "ai",
                "ai_tokens_used": 120,
                "ai_response_time_ms": 450,
                "conversation_channel": "messenger",
                "conversation_status": "resolved",
                "created_at": timestamp.replace(hour=13),
                "updated_at": timestamp.replace(hour=13),
            },
        ]
    )

    assert rows == [
        {
            "org_id": "org-a",
            "conversation_id": "conv-1",
            "event_date": date(2026, 4, 1),
            "conversation_channel": "messenger",
            "conversation_status": "resolved",
            "message_count": 2,
            "ai_message_count": 1,
            "user_message_count": 1,
            "total_ai_tokens_used": 120,
            "first_message_at": timestamp,
            "last_message_at": timestamp.replace(hour=13),
            "created_at": timestamp,
            "updated_at": timestamp.replace(hour=13),
            "avg_ai_response_time_ms": 450.0,
        }
    ]