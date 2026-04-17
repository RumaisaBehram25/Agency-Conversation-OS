"""Factory helpers for OLAP adapters."""

from functools import lru_cache

from app.config import settings
from app.olap.query import AthenaQueryAdapter, DisabledQueryAdapter, QueryAdapter, TrinoQueryAdapter
from app.olap.storage import DisabledObjectStorageAdapter, ObjectStorageAdapter, S3CompatibleObjectStorageAdapter


@lru_cache(maxsize=1)
def get_object_storage_adapter() -> ObjectStorageAdapter:
    """Return the configured object storage adapter for OLAP datasets."""
    if settings.olap_storage_provider == "s3":
        return S3CompatibleObjectStorageAdapter(settings)
    return DisabledObjectStorageAdapter(settings)


@lru_cache(maxsize=1)
def get_query_adapter() -> QueryAdapter:
    """Return the configured query adapter for historical analytics."""
    if settings.olap_query_provider == "trino":
        return TrinoQueryAdapter(settings)
    if settings.olap_query_provider == "athena":
        return AthenaQueryAdapter(settings)
    return DisabledQueryAdapter(settings)