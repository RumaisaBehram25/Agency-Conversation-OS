"""
Attora — Output Validator (Multi-Layer Hallucination Defense)

Validates AI-generated responses through four layers:
1. Banned phrase regex — medical claims, guarantees, diagnosis language
2. Price validation — any price must match the product catalog exactly
3. Compliance flag generation — logs what was caught
4. Kill switch topics — force human handoff

If any layer flags an issue, the response is replaced with a safe fallback.
"""

from __future__ import annotations

import logging
import re

from app.schemas.ai_engine import OrgConfig, ProductInfo, ValidationResult

logger = logging.getLogger(__name__)


# ── Layer 1: Banned Phrases ────────────────────────────────────

_BANNED_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Medical claims
    (re.compile(r"\b(cure[sd]?|heal[sd]?|treat[sd]?|remedy|therapeutic)\b", re.IGNORECASE),
     "medical_claim"),
    (re.compile(r"\b(diagnos[ei]s?|diagnosed|prescription|prescribe)\b", re.IGNORECASE),
     "medical_diagnosis"),
    (re.compile(r"\b(clinically proven|scientifically proven|medically proven)\b", re.IGNORECASE),
     "unsubstantiated_medical_claim"),
    (re.compile(r"\b(fda approved|fda cleared)\b", re.IGNORECASE),
     "fda_claim"),

    # Guarantee language
    (re.compile(r"\b(guarantee[sd]?|guaranteed)\s+(results?|outcome|success|weight loss|income)\b", re.IGNORECASE),
     "outcome_guarantee"),
    (re.compile(r"\b(100%|100 percent)\s+(effective|safe|guaranteed|success)\b", re.IGNORECASE),
     "absolute_guarantee"),
    (re.compile(r"\byou will (definitely|certainly|absolutely)\b", re.IGNORECASE),
     "certainty_language"),

    # Financial claims
    (re.compile(r"\b(guaranteed income|guaranteed (return|profit|earnings))\b", re.IGNORECASE),
     "financial_guarantee"),
    (re.compile(r"\b(get rich|make money fast|financial freedom guaranteed)\b", re.IGNORECASE),
     "financial_promise"),

    # Unsupported comparisons
    (re.compile(r"\b(best in the (world|market|industry)|number one|#1)\b", re.IGNORECASE),
     "superlative_claim"),
]


# ── Layer 4: Kill Switch Topics ────────────────────────────────

_KILL_SWITCH_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Adverse reactions
    (re.compile(r"\b(adverse (reaction|effect|event)|side effect|allergic reaction)\b", re.IGNORECASE),
     "adverse_reaction_discussion"),

    # Billing disputes
    (re.compile(r"\b(unauthorized charge|fraud|chargeback|billing dispute|stolen card)\b", re.IGNORECASE),
     "billing_dispute"),

    # Specific medical questions
    (re.compile(r"\b(what (dosage|dose)|how (much|many) should i take|drug interaction|contraindication)\b", re.IGNORECASE),
     "specific_medical_question"),

    # Legal threats
    (re.compile(r"\b(lawyer|attorney|lawsuit|sue|legal action|class action)\b", re.IGNORECASE),
     "legal_threat"),

    # Suicide/self-harm
    (re.compile(r"\b(suicid|self[- ]harm|kill myself|want to die|end my life)\b", re.IGNORECASE),
     "crisis_detection"),

    # Minors
    (re.compile(r"\bi am (\d|1[0-7])\s*(years? old|yr|yo)\b", re.IGNORECASE),
     "minor_detected"),
]

# Safe replacement for human handoff
_HANDOFF_RESPONSE = (
    "I want to make sure you get the best possible help with this. "
    "Let me connect you with a team member who can assist you directly."
)

# Safe replacement for compliance violations
_COMPLIANCE_REPLACEMENT = (
    "I appreciate your question! For the most accurate information on that, "
    "I'd recommend speaking with one of our team members."
)


def validate_output(
    response_text: str,
    org_config: OrgConfig,
) -> ValidationResult:
    """
    Run multi-layer output validation on an AI-generated response.

    Args:
        response_text: The AI-generated response to validate.
        org_config: Organization config (for product catalog price validation).

    Returns:
        ValidationResult with cleaned text, flags, and handoff indicators.
    """
    flags: list[str] = []
    needs_handoff = False
    handoff_reason = None
    cleaned_text = response_text

    # ── Layer 4 (check first — kill switch overrides everything) ──
    for pattern, flag_name in _KILL_SWITCH_PATTERNS:
        if pattern.search(response_text):
            flags.append(f"KILL_SWITCH:{flag_name}")
            needs_handoff = True
            handoff_reason = flag_name
            logger.warning(
                f"Kill switch triggered: {flag_name} in response: "
                f"{response_text[:200]}"
            )
            # Replace entire response with handoff message
            cleaned_text = _HANDOFF_RESPONSE
            return ValidationResult(
                is_valid=False,
                original_text=response_text,
                cleaned_text=cleaned_text,
                flags=flags,
                needs_human_handoff=True,
                handoff_reason=handoff_reason,
            )

    # ── Layer 1: Banned Phrases ────────────────────────────────
    for pattern, flag_name in _BANNED_PATTERNS:
        if pattern.search(response_text):
            flags.append(f"BANNED_PHRASE:{flag_name}")
            logger.info(
                f"Banned phrase detected: {flag_name} in response: "
                f"{response_text[:200]}"
            )

    # ── Layer 2: Price Validation ──────────────────────────────
    price_flags = _validate_prices(response_text, org_config.products)
    flags.extend(price_flags)

    # ── Layer 3: Apply replacements if flagged ─────────────────
    if flags:
        logger.warning(
            f"Output validation flagged {len(flags)} issues: {flags}"
        )
        # If there are banned phrases, replace the entire response
        banned_flags = [f for f in flags if f.startswith("BANNED_PHRASE:")]
        if banned_flags:
            cleaned_text = _COMPLIANCE_REPLACEMENT

    is_valid = len(flags) == 0

    return ValidationResult(
        is_valid=is_valid,
        original_text=response_text,
        cleaned_text=cleaned_text,
        flags=flags,
        needs_human_handoff=needs_handoff,
        handoff_reason=handoff_reason,
    )


def _validate_prices(
    response_text: str,
    products: list[ProductInfo],
) -> list[str]:
    """
    Validate that any prices mentioned in the response match the product catalog.

    Extracts dollar amounts from the response and checks them against
    known product prices.

    Returns list of price validation flags.
    """
    flags: list[str] = []

    # Extract prices from response text (handles $X, $X.XX, X USD, etc.)
    price_pattern = re.compile(
        r'(?:\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?))|'
        r'(?:(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|usd|dollars?))',
    )

    mentioned_prices = set()
    for match in price_pattern.finditer(response_text):
        price_str = match.group(1) or match.group(2)
        if price_str:
            try:
                price_val = float(price_str.replace(",", ""))
                mentioned_prices.add(price_val)
            except ValueError:
                continue

    if not mentioned_prices:
        return flags  # No prices mentioned

    # Build set of valid prices from product catalog
    valid_prices = set()
    for product in products:
        if product.price is not None:
            valid_prices.add(product.price)
        if product.conversion_value is not None:
            valid_prices.add(product.conversion_value)

    # Check each mentioned price
    for price in mentioned_prices:
        if price not in valid_prices:
            flags.append(f"PRICE_MISMATCH:${price:.2f}_not_in_catalog")
            logger.warning(
                f"Price ${price:.2f} mentioned in response but not found "
                f"in product catalog (valid: {valid_prices})"
            )

    return flags
