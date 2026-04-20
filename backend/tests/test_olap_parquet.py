from datetime import date, datetime, timezone

from app.olap.catalog import DatasetSpec
from app.olap.parquet import records_from_parquet_bytes, upsert_dataset_records


class DummyStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def dataset_prefix(self, dataset: DatasetSpec) -> str:
        return dataset.relative_prefix()

    def upload_bytes(self, key: str, payload: bytes, *, content_type: str = "application/octet-stream", metadata: dict[str, str] | None = None) -> str:
        self.objects[key] = payload
        return key

    def download_bytes(self, key: str) -> bytes:
        return self.objects[key]


def test_upsert_dataset_records_partitions_by_date_and_buckets_by_org():
    storage = DummyStorage()
    dataset = DatasetSpec(
        name="campaign_metrics_agg",
        partition_keys=("event_date",),
        record_keys=("org_id", "event_date", "meta_campaign_id"),
        bucket_keys=("org_id",),
        sort_keys=("org_id", "meta_campaign_id"),
    )
    timestamp = datetime(2026, 4, 17, tzinfo=timezone.utc)

    result = upsert_dataset_records(
        storage,
        dataset,
        [
            {
                "org_id": "org-b",
                "event_date": date(2026, 4, 1),
                "meta_campaign_id": "cmp-2",
                "spend": 5.0,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            {
                "org_id": "org-a",
                "event_date": date(2026, 4, 1),
                "meta_campaign_id": "cmp-9",
                "spend": 3.0,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            {
                "org_id": "org-a",
                "event_date": date(2026, 4, 1),
                "meta_campaign_id": "cmp-1",
                "spend": 7.0,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        ],
    )

    assert result["objects_written"] == 2
    assert sorted(result["keys"]) == [
        "campaign_metrics_agg/event_date=2026-04-01/bucket-org_id=org-a.parquet",
        "campaign_metrics_agg/event_date=2026-04-01/bucket-org_id=org-b.parquet",
    ]

    org_a_rows = records_from_parquet_bytes(
        storage.download_bytes("campaign_metrics_agg/event_date=2026-04-01/bucket-org_id=org-a.parquet")
    )
    assert [row["meta_campaign_id"] for row in org_a_rows] == ["cmp-1", "cmp-9"]


def test_daily_analytics_uses_date_partition_and_org_bucket():
    storage = DummyStorage()
    dataset = DatasetSpec(
        name="daily_analytics_compact",
        partition_keys=("event_date",),
        record_keys=("id",),
        bucket_keys=("org_id",),
        sort_keys=("org_id", "channel"),
    )
    timestamp = datetime(2026, 4, 17, tzinfo=timezone.utc)

    result = upsert_dataset_records(
        storage,
        dataset,
        [
            {
                "id": "row-1",
                "org_id": "org-b",
                "event_date": date(2026, 4, 2),
                "channel": "whatsapp",
                "new_conversations": 5,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            {
                "id": "row-2",
                "org_id": "org-a",
                "event_date": date(2026, 4, 2),
                "channel": "messenger",
                "new_conversations": 3,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        ],
    )

    assert sorted(result["keys"]) == [
        "daily_analytics_compact/event_date=2026-04-02/bucket-org_id=org-a.parquet",
        "daily_analytics_compact/event_date=2026-04-02/bucket-org_id=org-b.parquet",
    ]


def test_conversation_datasets_bucket_by_org_and_conversation():
    storage = DummyStorage()
    dataset = DatasetSpec(
        name="archived_messages",
        partition_keys=("event_date",),
        record_keys=("id",),
        bucket_keys=("org_id", "conversation_id"),
        sort_keys=("org_id", "conversation_id"),
    )
    timestamp = datetime(2026, 4, 17, tzinfo=timezone.utc)

    result = upsert_dataset_records(
        storage,
        dataset,
        [
            {
                "id": "msg-1",
                "org_id": "org-a",
                "conversation_id": "conv-2",
                "event_date": date(2026, 4, 3),
                "content": "hello",
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            {
                "id": "msg-2",
                "org_id": "org-a",
                "conversation_id": "conv-1",
                "event_date": date(2026, 4, 3),
                "content": "hi",
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        ],
    )

    assert sorted(result["keys"]) == [
        "archived_messages/event_date=2026-04-03/bucket-org_id=org-a-conversation_id=conv-1.parquet",
        "archived_messages/event_date=2026-04-03/bucket-org_id=org-a-conversation_id=conv-2.parquet",
    ]


def test_conversion_events_use_date_partition_and_org_conversation_bucket():
    storage = DummyStorage()
    dataset = DatasetSpec(
        name="conversion_events",
        partition_keys=("event_date",),
        record_keys=("id",),
        bucket_keys=("org_id", "conversation_id"),
        sort_keys=("org_id", "conversation_id"),
    )
    timestamp = datetime(2026, 4, 17, tzinfo=timezone.utc)

    result = upsert_dataset_records(
        storage,
        dataset,
        [
            {
                "id": "conv-evt-1",
                "org_id": "org-a",
                "conversation_id": "conv-9",
                "event_date": date(2026, 4, 4),
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            {
                "id": "conv-evt-2",
                "org_id": "org-a",
                "conversation_id": "conv-3",
                "event_date": date(2026, 4, 4),
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        ],
    )

    assert sorted(result["keys"]) == [
        "conversion_events/event_date=2026-04-04/bucket-org_id=org-a-conversation_id=conv-3.parquet",
        "conversion_events/event_date=2026-04-04/bucket-org_id=org-a-conversation_id=conv-9.parquet",
    ]