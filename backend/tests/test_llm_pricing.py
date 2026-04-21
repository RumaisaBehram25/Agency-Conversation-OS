"""
Tests for LLM cost computation.

Rates are hardcoded in the pricing module. These tests lock in the math
against known-good hand-computed values so regressions in either the
rate table or the formula get caught.
"""

from decimal import Decimal

import pytest

from app.services.llm_pricing import MODEL_PRICING_USD_PER_MTOK, compute_cost_usd


class TestComputeCostUsd:
    def test_sonnet_input_only(self):
        # 1M input tokens at $3.00/MTok = $3.00
        cost = compute_cost_usd("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=0)
        assert cost == Decimal("3.00")

    def test_sonnet_output_only(self):
        # 1M output tokens at $15.00/MTok = $15.00
        cost = compute_cost_usd("claude-sonnet-4-6", input_tokens=0, output_tokens=1_000_000)
        assert cost == Decimal("15.00")

    def test_sonnet_typical_call(self):
        # 2000 in + 500 out: (2000 * 3 + 500 * 15) / 1_000_000 = 0.0135
        cost = compute_cost_usd("claude-sonnet-4-6", input_tokens=2000, output_tokens=500)
        assert cost == Decimal("0.0135")

    def test_haiku_typical_call(self):
        # 500 in + 100 out: (500 * 1 + 100 * 5) / 1_000_000 = 0.001
        cost = compute_cost_usd(
            "claude-haiku-4-5-20251001", input_tokens=500, output_tokens=100
        )
        assert cost == Decimal("0.001")

    def test_cache_read_is_cheaper_than_input(self):
        # Sonnet: cache_read at $0.30 vs input at $3.00
        cached = compute_cost_usd(
            "claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_read_tokens=10_000
        )
        uncached = compute_cost_usd("claude-sonnet-4-6", input_tokens=10_000, output_tokens=0)
        assert cached * 10 == uncached

    def test_cache_write_is_more_expensive_than_input(self):
        # Sonnet: cache_write at $3.75 vs input at $3.00 (1.25x)
        written = compute_cost_usd(
            "claude-sonnet-4-6", input_tokens=0, output_tokens=0, cache_creation_tokens=10_000
        )
        plain = compute_cost_usd("claude-sonnet-4-6", input_tokens=10_000, output_tokens=0)
        assert written == plain * Decimal("1.25")

    def test_full_call_with_cache(self):
        # Sonnet call: 500 fresh in + 200 out + 2000 cache_read + 1000 cache_write
        # = (500*3 + 200*15 + 2000*0.30 + 1000*3.75) / 1M
        # = (1500 + 3000 + 600 + 3750) / 1M = 8850 / 1M = 0.00885
        cost = compute_cost_usd(
            "claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            cache_read_tokens=2000,
            cache_creation_tokens=1000,
        )
        assert cost == Decimal("0.00885")

    def test_unknown_model_returns_zero(self, caplog):
        cost = compute_cost_usd("gpt-4o-mini", input_tokens=1000, output_tokens=500)
        assert cost == Decimal("0")
        assert "Unknown model" in caplog.text

    def test_zero_tokens_returns_zero(self):
        cost = compute_cost_usd("claude-sonnet-4-6", input_tokens=0, output_tokens=0)
        assert cost == Decimal("0")

    @pytest.mark.parametrize(
        "model", ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
    )
    def test_rate_table_has_all_four_rates(self, model):
        rates = MODEL_PRICING_USD_PER_MTOK[model]
        assert {"input", "output", "cache_read", "cache_write"} == set(rates.keys())
        for v in rates.values():
            assert v > 0
