"""Object storage adapters for OLAP dataset exports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import boto3
from botocore.config import Config as BotoConfig
from app.config import Settings
from app.olap.catalog import DatasetSpec


@dataclass(frozen=True, slots=True)
class StorageObject:
    """Metadata about an object stored in the configured lake."""

    key: str
    uri: str
    size_bytes: int | None = None
    etag: str | None = None
    last_modified: datetime | None = None


class ObjectStorageAdapter(ABC):
    """Provider-agnostic interface for OLAP object storage."""

    provider: str

    def __init__(self, settings: Settings):
        self.settings = settings

    def dataset_prefix(self, dataset: DatasetSpec) -> str:
        """Return the dataset prefix below the lake root."""
        root_prefix = self.settings.olap_root_prefix
        if root_prefix:
            return f"{root_prefix}/{dataset.relative_prefix()}"
        return dataset.relative_prefix()

    def dataset_uri(self, dataset: DatasetSpec) -> str:
        """Return the provider URI for a dataset root."""
        return self.object_uri(self.dataset_prefix(dataset))

    @abstractmethod
    def object_uri(self, key: str) -> str:
        """Return the provider URI for a specific object key."""

    @abstractmethod
    def list_objects(self, prefix: str) -> list[StorageObject]:
        """List objects under a lake prefix."""

    @abstractmethod
    def download_bytes(self, key: str) -> bytes:
        """Download an object payload from storage."""

    @abstractmethod
    def upload_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a payload into object storage and return its URI."""


class DisabledObjectStorageAdapter(ObjectStorageAdapter):
    """Placeholder adapter used when no object storage provider is configured."""

    provider = "none"

    def object_uri(self, key: str) -> str:
        return f"disabled://{key.lstrip('/')}"

    def list_objects(self, prefix: str) -> list[StorageObject]:
        raise RuntimeError("OLAP object storage is disabled")

    def download_bytes(self, key: str) -> bytes:
        raise RuntimeError("OLAP object storage is disabled")

    def upload_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        raise RuntimeError("OLAP object storage is disabled")


class S3CompatibleObjectStorageAdapter(ObjectStorageAdapter):
    """S3-compatible adapter that works with both MinIO and Amazon S3."""

    provider = "s3"

    def object_uri(self, key: str) -> str:
        normalized_key = key.lstrip("/")
        return f"s3://{self.settings.olap_bucket}/{normalized_key}"

    def list_objects(self, prefix: str) -> list[StorageObject]:
        client = self._build_client()
        normalized_prefix = prefix.lstrip("/")
        paginator = client.get_paginator("list_objects_v2")
        objects: list[StorageObject] = []

        for page in paginator.paginate(Bucket=self.settings.olap_bucket, Prefix=normalized_prefix):
            for item in page.get("Contents", []):
                objects.append(
                    StorageObject(
                        key=item["Key"],
                        uri=self.object_uri(item["Key"]),
                        size_bytes=item.get("Size"),
                        etag=item.get("ETag"),
                        last_modified=item.get("LastModified"),
                    )
                )

        return objects

    def upload_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        client = self._build_client()
        normalized_key = key.lstrip("/")
        extra_args = {
            "ContentType": content_type,
        }
        if metadata:
            extra_args["Metadata"] = metadata

        client.put_object(
            Bucket=self.settings.olap_bucket,
            Key=normalized_key,
            Body=payload,
            **extra_args,
        )
        return self.object_uri(normalized_key)

    def download_bytes(self, key: str) -> bytes:
        client = self._build_client()
        normalized_key = key.lstrip("/")
        response = client.get_object(Bucket=self.settings.olap_bucket, Key=normalized_key)
        return response["Body"].read()

    def _build_client(self):
        return boto3.client(
            "s3",
            region_name=self.settings.olap_region,
            endpoint_url=self.settings.olap_endpoint or None,
            aws_access_key_id=self.settings.olap_access_key_id or None,
            aws_secret_access_key=self.settings.olap_secret_access_key or None,
            use_ssl=self.settings.olap_secure,
            config=BotoConfig(s3={"addressing_style": "path" if self.settings.olap_s3_force_path_style else "auto"}),
        )