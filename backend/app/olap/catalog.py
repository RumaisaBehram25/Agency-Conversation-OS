"""Dataset catalog for the phase 1 OLAP lane."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """Logical dataset definition shared across self-hosted and AWS providers."""

    name: str
    partition_keys: tuple[str, ...]
    record_keys: tuple[str, ...]
    bucket_keys: tuple[str, ...] = ()
    sort_keys: tuple[str, ...] = ()
    file_format: str = "parquet"

    def relative_prefix(self) -> str:
        """Return the dataset prefix below the configured lake root."""
        return self.name.strip("/")


AI_USAGE_EVENTS = DatasetSpec(
    name="ai_usage_events",
    partition_keys=("event_date",),
    record_keys=("id",),
    bucket_keys=("org_id", "conversation_id"),
    sort_keys=("org_id", "conversation_id"),
)

AI_USAGE_EVENTS_AGG = DatasetSpec(
    name="ai_usage_events_agg",
    partition_keys=("event_date",),
    record_keys=("org_id", "conversation_id", "event_date"),
    bucket_keys=("org_id", "conversation_id"),
    sort_keys=("org_id", "conversation_id"),
)

CAMPAIGN_METRICS = DatasetSpec(
    name="campaign_metrics",
    partition_keys=("event_date",),
    record_keys=("id",),
    bucket_keys=("org_id",),
    sort_keys=("org_id", "meta_campaign_id", "meta_adset_id", "meta_ad_id"),
)

CAMPAIGN_BREAKDOWNS = DatasetSpec(
    name="campaign_breakdowns",
    partition_keys=("event_date",),
    record_keys=("id",),
    bucket_keys=("org_id",),
    sort_keys=("org_id", "meta_campaign_id", "meta_adset_id", "meta_ad_id", "breakdown_type", "breakdown_key"),
)

CAMPAIGN_METRICS_AGG = DatasetSpec(
    name="campaign_metrics_agg",
    partition_keys=("event_date",),
    record_keys=("org_id", "event_date", "meta_campaign_id"),
    bucket_keys=("org_id",),
    sort_keys=("org_id", "meta_campaign_id"),
)

DAILY_ANALYTICS = DatasetSpec(
    name="daily_analytics",
    partition_keys=("event_date",),
    record_keys=("id",),
    bucket_keys=("org_id",),
    sort_keys=("org_id", "channel"),
)

DAILY_ANALYTICS_COMPACT = DatasetSpec(
    name="daily_analytics_compact",
    partition_keys=("event_date",),
    record_keys=("id",),
    bucket_keys=("org_id",),
    sort_keys=("org_id", "channel"),
)

CONVERSION_EVENTS = DatasetSpec(
    name="conversion_events",
    partition_keys=("event_date",),
    record_keys=("id",),
    bucket_keys=("org_id", "conversation_id"),
    sort_keys=("org_id", "conversation_id"),
)

ARCHIVED_MESSAGES = DatasetSpec(
    name="archived_messages",
    partition_keys=("event_date",),
    record_keys=("id",),
    bucket_keys=("org_id", "conversation_id"),
    sort_keys=("org_id", "conversation_id"),
)

ARCHIVED_MESSAGES_AGG = DatasetSpec(
    name="archived_messages_agg",
    partition_keys=("event_date",),
    record_keys=("org_id", "conversation_id", "event_date"),
    bucket_keys=("org_id", "conversation_id"),
    sort_keys=("org_id", "conversation_id"),
)


OLAP_DATASETS: dict[str, DatasetSpec] = {
    dataset.name: dataset
    for dataset in (
        AI_USAGE_EVENTS,
        AI_USAGE_EVENTS_AGG,
        CAMPAIGN_METRICS,
        CAMPAIGN_BREAKDOWNS,
        CAMPAIGN_METRICS_AGG,
        DAILY_ANALYTICS,
        DAILY_ANALYTICS_COMPACT,
        CONVERSION_EVENTS,
        ARCHIVED_MESSAGES,
        ARCHIVED_MESSAGES_AGG,
    )
}