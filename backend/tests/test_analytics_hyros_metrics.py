"""Unit tests for Hyros-derived analytics helpers (purchase buckets + cost ratios)."""

from datetime import date

import pytest

from app.schemas.analytics import PurchasesDailyPoint
from app.services.analytics_service import (
    build_purchases_over_time_buckets,
    hyros_cost_per_conversation_safe,
    hyros_cost_per_purchase_safe,
)


@pytest.mark.parametrize(
    ("spend", "count", "expected"),
    [
        (0.0, 5, None),
        (100.0, 0, None),
        (-1.0, 3, None),
        (100.0, 4, 25.0),
        (33.33, 3, 11.11),
    ],
)
def test_hyros_cost_per_purchase_safe(spend: float, count: int, expected: float | None) -> None:
    assert hyros_cost_per_purchase_safe(spend, count) == expected


@pytest.mark.parametrize(
    ("spend", "count", "expected"),
    [
        (0.0, 10, None),
        (50.0, 0, None),
        (50.0, 5, 10.0),
    ],
)
def test_hyros_cost_per_conversation_safe(
    spend: float, count: int, expected: float | None
) -> None:
    assert hyros_cost_per_conversation_safe(spend, count) == expected


def test_build_purchases_over_time_buckets_empty_span() -> None:
    d = date(2025, 6, 1)
    points = build_purchases_over_time_buckets({}, d, d)
    assert points == [PurchasesDailyPoint(date=d, purchases=0)]


def test_build_purchases_over_time_buckets_fills_zeros() -> None:
    d0 = date(2025, 6, 1)
    d2 = date(2025, 6, 3)
    points = build_purchases_over_time_buckets({d2: 2}, d0, d2)
    assert len(points) == 3
    assert points[0] == PurchasesDailyPoint(date=d0, purchases=0)
    assert points[1] == PurchasesDailyPoint(date=date(2025, 6, 2), purchases=0)
    assert points[2] == PurchasesDailyPoint(date=d2, purchases=2)


def test_build_purchases_over_time_buckets_sum_matches_total() -> None:
    counts = {
        date(2025, 1, 1): 3,
        date(2025, 1, 3): 1,
    }
    series = build_purchases_over_time_buckets(counts, date(2025, 1, 1), date(2025, 1, 5))
    assert sum(p.purchases for p in series) == 4
