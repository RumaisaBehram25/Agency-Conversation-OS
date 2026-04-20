"""Checkpoint helpers for scheduled OLAP exports and parity runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.olap.storage import ObjectStorageAdapter


def load_checkpoint(
    storage: ObjectStorageAdapter,
    *,
    job_name: str,
    scope: str = "global",
) -> dict[str, Any] | None:
    """Load a checkpoint document from object storage if it exists."""
    key = checkpoint_key(job_name, scope)
    try:
        payload = storage.download_bytes(key)
    except Exception:
        return None
    return json.loads(payload.decode("utf-8"))


def save_checkpoint(
    storage: ObjectStorageAdapter,
    *,
    job_name: str,
    scope: str = "global",
    payload: dict[str, Any],
) -> str:
    """Persist a checkpoint document into object storage."""
    document = dict(payload)
    document.setdefault("job_name", job_name)
    document.setdefault("scope", scope)
    document["updated_at"] = datetime.now(timezone.utc).isoformat()
    key = checkpoint_key(job_name, scope)
    encoded = json.dumps(document, sort_keys=True).encode("utf-8")
    return storage.upload_bytes(key, encoded, content_type="application/json")


def checkpoint_key(job_name: str, scope: str) -> str:
    """Build the object-storage key for a checkpoint document."""
    root = settings.olap_checkpoint_root_prefix
    normalized_job = job_name.strip("/")
    normalized_scope = scope.strip("/") or "global"
    if root:
        return f"{root}/{normalized_job}/{normalized_scope}.json"
    return f"{normalized_job}/{normalized_scope}.json"