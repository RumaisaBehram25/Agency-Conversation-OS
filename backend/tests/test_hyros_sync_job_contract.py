"""Hyros batch sync job aggregates orgs and exposes stable response keys."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import cron as cron_api
from app.config import settings
from app.database import get_db
from app.jobs.hyros_sync import sync_hyros_purchases
from app.main import app
from app.models.organization import Organization
from tests.test_api_contracts import FakeResult, QueueSession


@pytest.mark.asyncio
async def test_sync_hyros_purchases_empty_orgs_response_keys() -> None:
    """No orgs → zeroed aggregates; manual cron / tooling can rely on these keys."""
    session = QueueSession(
        [
            FakeResult(scalars=[]),  # select(Organization) → no rows
        ]
    )
    out = await sync_hyros_purchases(session)

    assert out["orgs_synced"] == 0
    assert out["orgs_skipped"] == 0
    assert out["orgs_skipped_no_api_key"] == 0
    assert out["orgs_decrypt_failed"] == 0
    assert out["sales_scanned"] == 0
    assert out["unmatched_sales"] == 0
    assert out["purchases_found"] == 0

    required = (
        "orgs_synced",
        "orgs_skipped",
        "orgs_skipped_no_api_key",
        "orgs_decrypt_failed",
        "sales_scanned",
        "unmatched_sales",
        "purchases_found",
        "subscribers_scanned",
    )
    for key in required:
        assert key in out


@pytest.mark.asyncio
async def test_sync_hyros_purchases_skips_org_without_key_counts_orgs_skipped() -> None:
    org = Organization(
        id=uuid.uuid4(),
        name="o",
        slug="o-test-hyros-skip",
        attora_api_key="encrypted-placeholder",
        hyros_api_key=None,
    )
    session = QueueSession(
        [
            FakeResult(scalars=[org]),
        ]
    )
    out = await sync_hyros_purchases(session)

    assert out["orgs_synced"] == 0
    assert out["orgs_skipped"] == 1
    assert out["orgs_skipped_no_api_key"] == 1


def test_post_cron_hyros_sync_returns_same_shape_as_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /api/cron/hyros-sync mirrors the job dict (manual cron curl contract)."""

    async def fake_sync(_db):
        return await sync_hyros_purchases(
            QueueSession([FakeResult(scalars=[])])
        )

    # `cron` holds its own import of `sync_hyros_purchases` — patch that binding.
    monkeypatch.setattr(cron_api, "sync_hyros_purchases", fake_sync)

    async def override_db():
        yield QueueSession()

    app.dependency_overrides[get_db] = override_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/cron/hyros-sync",
                headers={"X-Cron-Secret": settings.cron_secret},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["orgs_synced"] == 0
    assert payload["orgs_skipped"] == 0
    assert payload["sales_scanned"] == 0
    assert "purchases_found" in payload
    assert "unmatched_sales" in payload
    assert "orgs_decrypt_failed" in payload
