"""Pure helpers for Hyros traffic-source spend allocation (no DB)."""

from app.services.analytics_service import (
    hyros_allocate_spend_by_purchase_shares,
    hyros_cost_per_conversation_safe,
    hyros_cost_per_purchase_safe,
    hyros_traffic_bucket_to_api_source,
)


def test_allocate_splits_campaign_spend_by_purchaser_share() -> None:
    spend = {"c1": 100.0}
    counts = [("fb", "c1", 60), ("ig", "c1", 40)]
    out = hyros_allocate_spend_by_purchase_shares(spend, counts)
    assert out["fb"] == 60.0
    assert out["ig"] == 40.0


def test_allocate_zero_spend_returns_empty() -> None:
    spend = {"c1": 0.0}
    counts = [("fb", "c1", 10)]
    assert hyros_allocate_spend_by_purchase_shares(spend, counts) == {}


def test_allocate_skips_null_campaign_purchasers() -> None:
    spend = {"c1": 50.0}
    counts = [("organic", None, 5), ("fb", "c1", 5)]
    out = hyros_allocate_spend_by_purchase_shares(spend, counts)
    assert out == {"fb": 50.0}


def test_allocate_multiple_campaigns_no_double_count() -> None:
    spend = {"a": 100.0, "b": 200.0}
    counts = [
        ("x", "a", 50),
        ("y", "a", 50),
        ("x", "b", 25),
        ("y", "b", 75),
    ]
    out = hyros_allocate_spend_by_purchase_shares(spend, counts)
    assert out["x"] == 100.0  # 50% of 100 + 25% of 200
    assert out["y"] == 200.0  # 50% of 100 + 75% of 200


def test_cpp_ccp_null_when_zero_spend_or_denominator() -> None:
    assert hyros_cost_per_purchase_safe(0.0, 3) is None
    assert hyros_cost_per_purchase_safe(100.0, 0) is None
    assert hyros_cost_per_conversation_safe(0.0, 10) is None
    assert hyros_cost_per_conversation_safe(30.0, 0) is None


def test_organic_bucket_api_mapping() -> None:
    assert hyros_traffic_bucket_to_api_source("organic") is None
    assert hyros_traffic_bucket_to_api_source("Instagram") == "Instagram"


def test_allocate_total_allocated_spend_equals_campaign_facts() -> None:
    """Each campaign's Meta spend is split across buckets — sum never exceeds total."""
    spend = {"c1": 100.0, "c2": 50.0}
    counts = [
        ("fb", "c1", 30),
        ("ig", "c1", 70),
        ("fb", "c2", 10),
        ("ig", "c2", 40),
    ]
    out = hyros_allocate_spend_by_purchase_shares(spend, counts)
    total_allocated = sum(out.values())
    total_facts = sum(spend.values())
    assert total_allocated <= total_facts + 1e-6
    assert abs(total_allocated - total_facts) < 0.01
