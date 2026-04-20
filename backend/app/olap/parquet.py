"""Parquet helpers for phase 1 OLAP exports and parity checks."""

from __future__ import annotations

import io
import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from app.olap.catalog import DatasetSpec
from app.olap.storage import ObjectStorageAdapter


def normalize_value(value: Any) -> Any:
    """Convert SQLAlchemy and Python values into Parquet-friendly primitives."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    return value


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single record before Parquet serialization."""
    return {key: normalize_value(value) for key, value in record.items()}


def parquet_bytes_from_records(records: list[dict[str, Any]]) -> bytes:
    """Serialize normalized records to a Parquet payload."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not records:
        raise ValueError("Cannot serialize an empty record set to Parquet")

    table = pa.Table.from_pylist([normalize_record(record) for record in records])
    sink = io.BytesIO()
    pq.write_table(table, sink, compression="snappy")
    return sink.getvalue()


def records_from_parquet_bytes(payload: bytes) -> list[dict[str, Any]]:
    """Read records from a Parquet payload."""
    import pyarrow.parquet as pq

    table = pq.read_table(io.BytesIO(payload))
    return table.to_pylist()


def write_dataset_records(
    storage: ObjectStorageAdapter,
    dataset: DatasetSpec,
    records: list[dict[str, Any]],
    *,
    file_name: str = "data.parquet",
) -> dict[str, Any]:
    """Write records into partitioned dataset objects, overwriting each partition file."""
    if not records:
        return {
            "rows_written": 0,
            "objects_written": 0,
            "keys": [],
        }

    groups = _group_records(dataset, records)

    keys: list[str] = []
    for (partition_path, bucket_file_name), partition_records in groups.items():
        key = _dataset_object_key(storage, dataset, partition_path, bucket_file_name, file_name)
        payload = parquet_bytes_from_records(partition_records)
        storage.upload_bytes(
            key,
            payload,
            content_type="application/vnd.apache.parquet",
            metadata={
                "dataset": dataset.name,
                "rows": str(len(partition_records)),
            },
        )
        keys.append(key)

    return {
        "rows_written": len(records),
        "objects_written": len(keys),
        "keys": keys,
    }


def upsert_dataset_records(
    storage: ObjectStorageAdapter,
    dataset: DatasetSpec,
    records: list[dict[str, Any]],
    *,
    file_name: str = "data.parquet",
) -> dict[str, Any]:
    """Merge incoming records into canonical per-partition Parquet objects."""
    if not records:
        return {
            "rows_written": 0,
            "objects_written": 0,
            "keys": [],
        }

    groups = _group_records(dataset, records)

    keys: list[str] = []
    for (partition_path, bucket_file_name), partition_records in groups.items():
        key = _dataset_object_key(storage, dataset, partition_path, bucket_file_name, file_name)
        merged_records = _merge_records(
            existing_records=_load_existing_partition_records(storage, key),
            incoming_records=partition_records,
            record_keys=dataset.record_keys,
        )
        merged_records = _sort_records(merged_records, dataset.sort_keys)
        payload = parquet_bytes_from_records(merged_records)
        storage.upload_bytes(
            key,
            payload,
            content_type="application/vnd.apache.parquet",
            metadata={
                "dataset": dataset.name,
                "rows": str(len(merged_records)),
            },
        )
        keys.append(key)

    return {
        "rows_written": len(records),
        "objects_written": len(keys),
        "keys": keys,
    }


def _partition_value(value: Any) -> str:
    """Convert partition values into stable path fragments."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _group_records(
    dataset: DatasetSpec,
    records: list[dict[str, Any]],
) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        normalized = normalize_record(record)
        partition_path = _partition_path(dataset, normalized)
        bucket_file_name = _bucket_file_name(dataset, normalized)
        groups[(partition_path, bucket_file_name)].append(normalized)

    if dataset.sort_keys:
        for group_key, group_records in groups.items():
            groups[group_key] = _sort_records(group_records, dataset.sort_keys)

    return groups


def _partition_path(dataset: DatasetSpec, record: dict[str, Any]) -> str:
    partition_segments = []
    for key in dataset.partition_keys:
        if key not in record:
            raise ValueError(f"Missing partition key '{key}' for dataset '{dataset.name}'")
        partition_segments.append(f"{key}={_partition_value(record[key])}")
    return "/".join(partition_segments)


def _bucket_file_name(dataset: DatasetSpec, record: dict[str, Any]) -> str | None:
    if not dataset.bucket_keys:
        return None

    bucket_segments = []
    for key in dataset.bucket_keys:
        if key not in record:
            raise ValueError(f"Missing bucket key '{key}' for dataset '{dataset.name}'")
        bucket_value = _safe_file_fragment(_partition_value(record[key]))
        bucket_segments.append(f"{key}={bucket_value}")
    return f"bucket-{'-'.join(bucket_segments)}.parquet"


def _dataset_object_key(
    storage: ObjectStorageAdapter,
    dataset: DatasetSpec,
    partition_path: str,
    bucket_file_name: str | None,
    default_file_name: str,
) -> str:
    file_name = bucket_file_name or default_file_name
    if partition_path:
        return f"{storage.dataset_prefix(dataset)}/{partition_path}/{file_name}"
    return f"{storage.dataset_prefix(dataset)}/{file_name}"


def _sort_records(records: list[dict[str, Any]], sort_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not sort_keys:
        return list(records)
    return sorted(records, key=lambda record: tuple(_sortable_value(record.get(key)) for key in sort_keys))


def _sortable_value(value: Any) -> tuple[int, Any]:
    if value is None:
        return (0, "")
    if isinstance(value, list):
        return (1, tuple(_sortable_value(item) for item in value))
    if isinstance(value, dict):
        return (1, tuple(sorted((str(key), _sortable_value(item)) for key, item in value.items())))
    return (1, str(value))


def _safe_file_fragment(value: str) -> str:
    return value.replace("/", "_").replace(" ", "_")


def _load_existing_partition_records(
    storage: ObjectStorageAdapter,
    key: str,
) -> list[dict[str, Any]]:
    try:
        payload = storage.download_bytes(key)
    except Exception:
        return []
    return records_from_parquet_bytes(payload)


def _merge_records(
    *,
    existing_records: list[dict[str, Any]],
    incoming_records: list[dict[str, Any]],
    record_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not record_keys:
        return incoming_records

    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in existing_records:
        merged[_record_key(record, record_keys)] = record
    for record in incoming_records:
        merged[_record_key(record, record_keys)] = record
    return list(merged.values())


def _record_key(record: dict[str, Any], record_keys: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(record.get(key) for key in record_keys)