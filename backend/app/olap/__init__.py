"""Shared OLAP adapter exports for the backend phase 1 rollout."""

from app.olap.catalog import OLAP_DATASETS
from app.olap.factory import get_object_storage_adapter, get_query_adapter

__all__ = [
    "OLAP_DATASETS",
    "get_object_storage_adapter",
    "get_query_adapter",
]