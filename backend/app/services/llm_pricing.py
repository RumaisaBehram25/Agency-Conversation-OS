"""
Attora — LLM Pricing

USD cost computation for Anthropic model usage. Rates are per million tokens.
Last verified against https://www.anthropic.com/pricing on 2026-04-14.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, Decimal]] = {
    "claude-sonnet-4-6": {
        "input": Decimal("3.00"),
        "output": Decimal("15.00"),
        "cache_write": Decimal("3.75"),
        "cache_read": Decimal("0.30"),
    },
    "claude-haiku-4-5-20251001": {
        "input": Decimal("1.00"),
        "output": Decimal("5.00"),
        "cache_write": Decimal("1.25"),
        "cache_read": Decimal("0.10"),
    },
}

_MTOK = Decimal("1000000")


def compute_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> Decimal:
    """
    Compute the USD cost for a single Anthropic API call.

    Anthropic reports `input_tokens` as the count of *non-cached* input tokens.
    Cache read and cache creation tokens are billed separately.
    """
    rates = MODEL_PRICING_USD_PER_MTOK.get(model)
    if rates is None:
        logger.warning(
            "Unknown model %s in cost calc; returning $0. "
            "Add it to MODEL_PRICING_USD_PER_MTOK.",
            model,
        )
        return Decimal("0")

    cost = (
        rates["input"] * Decimal(input_tokens)
        + rates["output"] * Decimal(output_tokens)
        + rates["cache_read"] * Decimal(cache_read_tokens)
        + rates["cache_write"] * Decimal(cache_creation_tokens)
    ) / _MTOK

    return cost
