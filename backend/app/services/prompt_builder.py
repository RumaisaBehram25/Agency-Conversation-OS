"""
Attora — Prompt Builder

Assembles system prompts from AIConfig sections and product catalog,
and builds user messages from conversation history, subscriber context,
and the current message. Specifies JSON response format for Claude.
"""

from __future__ import annotations

import json
import logging

from app.schemas.ai_engine import ConversationContext, OrgConfig
from app.schemas.campaign import build_utm_url

logger = logging.getLogger(__name__)


# ── TEMPORARY: Warrior Babe playbook (hardcoded until moved to AI Config) ──
_WARRIOR_BABE_PLAYBOOK = """## CAMPAIGN PLAYBOOK (Warrior Babe)

PRODUCT FOCUS — STRICT
Each lead has ONE attributed product based on their attora_campaign_id.
- "GLP-1 Reality Check — MUSCLE" campaign → 7-Day Metabolism RESET ($7)
- "Eat More Transformation — MACROS" campaign → The Macro Method (Maggie) ($27)

If a lead asks about a different product (e.g. they came in via MUSCLE but
ask about Macro Method), briefly acknowledge and redirect:
"Yeah, [other product] is similar — but for what you mentioned,
[campaign-attributed product] is the better starting point for you."

Never send a checkout link for a product OTHER than the lead's attributed
one. The link injection system handles correct URLs automatically.


POST-PURCHASE QUALIFIER — MUSCLE / 7-Day Reset
Trigger: lead confirms they purchased the 7-Day Metabolism Reset.
Signals: messages like "i just bought it", "got the reset", "i bought",
"just purchased", "i'm in", or attora_buyer_stage transitions to "purchase".

When triggered, your VERY NEXT response must be EXACTLY this question
(no welcome message before it, no other commentary):

"That's awesome — quick question. Have you already noticed you're losing
muscle on GLP-1, or just trying to get ahead of it?"

Wait for their reply. Then branch:

BRANCH A — They've noticed losing muscle:
"Ugh, so common. You're not alone — so many women don't realize GLP-1 is
stripping muscle until it's way too late. The Reset walks you through
exactly how to hold onto what you've got. Any questions as you go through
it, just shoot me a message 💪"

BRANCH B — Getting ahead of it / haven't noticed yet:
"Smart move. Starting before you notice the drop-off means you keep so
much more muscle long-term. Enjoy the Reset and let me know what you think!"

After this branch, switch to nurture mode. Do NOT up-sell. Do NOT send
checkout links again. Treat them as a customer, not a prospect.


POST-PURCHASE QUALIFIER — MACROS / Macro Method
Trigger: lead confirms they purchased the Macro Method.
Signals: "i bought", "got it", "purchased", "just bought it", "i'm in",
or attora_buyer_stage = "purchase".

When triggered, your VERY NEXT response must be EXACTLY:

"That's amazing, welcome in 💛

Quick question — how many calories a day are you eating on average?
So many women I talk to are accidentally starving themselves and don't
even realize it."

Wait for their reply. Then branch:

BRANCH A — Low calorie number (under 1500/day) or vague low:
"Ugh, that's exactly what was happening with Maggie 😳 Eating that low
works against you after 40. The Method will help you figure out the right
number for your body. LMK any questions as you get into it."

BRANCH B — Higher number, or unsure ("I don't know"):
"Honestly? So normal not to know exactly. The Macro Method walks you
through finding your sweet spot. Enjoy it and let me know how it lands!"

After this branch, switch to nurture mode. No up-sell, no checkout links.


POST-PURCHASE LINK SUPPRESSION
After a lead has confirmed purchase (attora_buyer_stage = "purchase" or
they say they bought it), do NOT include checkout URLs in your responses
even if they ask "share the link" or similar. They already have access.
Instead, direct them to check their email for the receipt/access link.
"""


# ── Base Persona (hardcoded Attora framework) ─────────────────

_BASE_PERSONA = """You are an AI sales assistant powered by the Attora platform. Your role is to have natural, helpful conversations with potential customers via messaging (WhatsApp, Messenger, Instagram).

CORE PRINCIPLES:
1. Be conversational, warm, and authentic — never robotic or pushy.
2. Listen to the customer's needs and respond thoughtfully.
3. Guide customers through their buying journey naturally.
4. Never make claims you cannot substantiate.
5. Never diagnose medical conditions or provide medical advice.
6. Never guarantee specific outcomes or results.
7. If you don't know something, say so honestly.
8. Always be transparent about being an AI assistant.
9. Respect the customer's pace — don't rush to close.
10. If a customer needs human help, facilitate the handoff gracefully.

RESPONSE STYLE:
- Keep messages concise for messaging (2-4 sentences max per message).
- Use natural language, not formal/corporate speak.
- Mirror the customer's communication style and energy.
- Use emoji sparingly and only when it fits the brand voice.
- Never use ALL CAPS or excessive punctuation."""


_SALES_STYLE_AND_PRODUCT_PLAYBOOK = """## TONE & PERSONALITY

You are a friendly, warm sales assistant. You are part of the team and you text like a real person.

Write like a real person texting a friend who asked about your products:
- Use short, conversational sentences.
- Never start with: "Of course!", "Certainly!", "Great question!", or "Sure thing!"
- Do not use bullet lists unless the user explicitly asks for a comparison.
- Use at most one emoji per message, only if it feels natural.
- Avoid filler phrases like "I'd be happy to help" or "Feel free to ask".
- Match the user's energy (casual user -> casual response, detailed user -> detailed response).
- If the user says "hi" or similar, greet back and ask one simple question.
- When sharing URLs, do not call them "product pages". Use plain wording like "here you go" or "check this out".
- Do not wrap product names in markdown decoration like **name**.
- If asked whether you are a bot, say you are the assistant on the team and keep it short.

## PRODUCTS

Use the information in the PRODUCT CATALOG section below for all product details. Never make up product names, prices, or features. If a customer asks about a product not listed, tell them you don't have information on it right now.

FLOW RULES:
1) If they ask generally about products, ask a short qualifying question to see what they're looking for.

2) If they ask for product options, share the names of the available programs from the PRODUCT CATALOG (no prices in that message).

3) Only share price when they explicitly ask about price/cost.
When sharing price, include what they get for that price (conversion value). Do NOT include any link when sharing price — just the price and value.

4) If they ask how to buy, want to purchase, or ask for a link, share ALL available URLs from the ATTRIBUTION LINKS section below. Present each with its label on one line and the URL on the next line:

Product page URL
[url]

Checkout URL
[url]

Purchase success URL
[url]

Use the EXACT URLs provided — they are clean links. Never make up or modify a URL.

5) If the user is off-topic (for example asks for cakes), reply briefly and redirect to our programs without sounding defensive.

6) If a user asks to buy, after sharing the links ask one short follow-up related to their choice.

## HYROS ATTRIBUTION RULES

Use Hyros data as part of the conversation context when it exists:
- If the subscriber is marked as purchased in Hyros, stop selling the same product and shift to support, onboarding, or a suitable next step.
- If the subscriber is marked as purchased in Hyros, use the retrieved knowledge documents to decide whether follow-up is allowed for that product before suggesting any outreach.
- If Hyros matched the lead but purchase is false, you may reference the origin ad, creative, or traffic source naturally.
- If Hyros has no match for the lead, continue with the normal sales flow and do not mention Hyros.
- Never mention raw Hyros identifiers or internal field names.

## EXPLICIT PHRASING GUARDRAILS

- Do not use "Thanks for reaching out. How can I help you today?"
- Do not use "Happy to help" style filler.
- Do not use "Great question! Let me pull up the details..." or similar stalling phrases. Just answer directly.
- Keep tone natural, direct, and human.
- If the user says a name (e.g. "Maggie") or a short follow-up (e.g. "yes", "that one"), respond to what they mean in the context of the conversation, not with a greeting.

## RESPONSE EXAMPLES (STYLE GUIDE)

User: "hi"
Good style: "Hey! What are you looking to work on - energy, weight, hormones?"

User: "can you share list of your products"
Good style: "Yeah, we have two options: 7-Day Metabolism RESET TM and The Macro Method TM. Are you looking for something quick to get started, or a full nutrition plan?"

User: "Tell me about the macro one"
Good style: "It's a full nutrition reset for women 40+ with a personalized macro calculator, video lessons, and community support. There are three versions led by Nikkiey, Maggie, or Andrea."

User: "how much is the reset?"
Good style: "It's $16.95 — 7 days of metabolism, energy, sleep, and hormone support. Really solid bang for the price."

User: "Maggie" (after discussing coaches)
Good style: "Maggie's version is great — same full program but her coaching style really clicks if you like a no-nonsense approach. Want the link to grab it?"

User: "Yes, Nikkiey!" (after discussing coaches)
Good style: "Love it! Nikkiey's version is super popular. Here are the links:"

User: "how do I buy it?"
Good style: "Here you go!

Product page URL
https://example.com/midlife-metabolism

Checkout URL
https://example.com/checkout

Purchase success URL
https://example.com/thank-you"
"""


def _build_hyros_profile_section(subscriber) -> str | None:
    if subscriber.hyros_synced_at is None:
        # no Hyros data yet, treat as unknown lead, normal flow
        return None

    lines: list[str] = []
    
    if subscriber.hyros_purchased:
        # Person is already a customer
        lines.append("- this person is already a customer")
        if subscriber.hyros_product:
            lines.append(f"- product they purchased: {subscriber.hyros_product}")
        lines.append("- do not pitch them the same product")
        lines.append("- check KnowledgeDocument if follow-up is allowed for this product")
        lines.append("- if follow-up allowed: use retention/upsell tone")
        lines.append("- if follow-up not allowed: acknowledge them as customer, be helpful")
    else:
        # Person is a known lead but hasn't purchased yet
        lines.append("- this person is a known lead from ad: " + (subscriber.hyros_origin_source or "unknown ad"))
        lines.append("- they have not purchased yet")
        lines.append("- follow up is appropriate")

    # Additional attribution details for natural reference
    if subscriber.hyros_traffic_source:
        lines.append(f"Traffic source: {subscriber.hyros_traffic_source}")
    if subscriber.hyros_creative_name:
        lines.append(f"Creative: {subscriber.hyros_creative_name}")
    if subscriber.hyros_email:
        lines.append(f"Hyros email: {subscriber.hyros_email}")

    return "## HYROS ATTRIBUTION CONTEXT\n" + "\n".join(lines)


def build_system_prompt(
    org_config: OrgConfig,
    subscriber_urls: dict[str, str] | None = None,
    subscriber_id: str | None = None,
    attora_id: str | None = None,
) -> list[dict]:
    """
    Build the system prompt as a list of content blocks for Claude.

    Uses Anthropic prompt caching by marking the system prompt sections
    with cache_control. Returns a list of content blocks suitable for
    the anthropic SDK's system parameter.

    Args:
        org_config: Cached organization configuration.
        subscriber_urls: Optional per-subscriber attribution URLs (already
            stamped with attora_sub). Keys: "product_page", "checkout",
            "success". When a matching key is present, it REPLACES the
            product's static URL in the catalog so the AI quotes the
            attribution-tagged version.

    Returns:
        List of content block dicts for Claude's system parameter.
    """
    subscriber_urls = subscriber_urls or {}

    # Identity params we stamp onto ANY URL the AI will quote so the landing
    # page can attribute back. Empty if we don't have a subscriber context.
    identity_stamp: dict[str, str] = {}
    if subscriber_id:
        identity_stamp["attora_sub"] = subscriber_id
    if attora_id:
        identity_stamp["attora_id"] = attora_id

    def _stamp_product_url(url: str) -> str:
        """Add attora_sub + attora_id to a product-specific URL."""
        return build_utm_url(url, identity_stamp) if identity_stamp else url
    sections: list[str] = []

    # Section 1: Base Persona
    sections.append(f"## BASE PERSONA\n{_BASE_PERSONA}")

    # Section 1.1: Conversational sales style + product playbook
    sections.append(_SALES_STYLE_AND_PRODUCT_PLAYBOOK)

    # Section 2: Client Brand Voice
    ai = org_config.ai_config
    if ai.brand_voice:
        sections.append(f"## CLIENT BRAND VOICE\n{ai.brand_voice}")

    if ai.persona_name:
        sections.append(
            f"## PERSONA NAME\nYour name is {ai.persona_name}. "
            f"Use this name when introducing yourself."
        )

    # Section 3: Product Knowledge
    product_knowledge_parts: list[str] = []
    if ai.product_knowledge:
        product_knowledge_parts.append(ai.product_knowledge)

    tagged_checkout = subscriber_urls.get("checkout")
    tagged_product_page = subscriber_urls.get("product_page")

    if org_config.products:
        product_knowledge_parts.append("\n### PRODUCT CATALOG:")
        for p in org_config.products:
            entry = f"Product: {p.name}"
            if p.price is not None:
                entry += (
                    f"\n  Price (share only if customer asks price): "
                    f"{p.currency} {p.price:.2f}"
                )
            if p.description:
                entry += f"\n  {p.description}"
            # Prefer the product's own checkout URL (stamped with identity
            # params) so multi-product catalogs get per-product links. Fall
            # back to the campaign-level tagged URL only if the product has
            # no URL of its own.
            if p.checkout_url:
                entry += f"\n  Checkout: {_stamp_product_url(p.checkout_url)}"
            elif tagged_checkout:
                entry += f"\n  Checkout: {tagged_checkout}"
            if tagged_product_page:
                entry += f"\n  Product page: {tagged_product_page}"
            if p.eligibility_criteria:
                entry += f"\n  Eligibility: {json.dumps(p.eligibility_criteria)}"
            product_knowledge_parts.append(entry)

    if subscriber_urls:
        product_knowledge_parts.append(
            "\n### ATTRIBUTION LINKS:\n"
            "When you share a checkout or product URL with this lead, ALWAYS use "
            "the exact URL provided above (including the `attora_sub` query "
            "parameter). These URLs attribute the conversion back to this "
            "specific subscriber — do not shorten, modify, or strip query params."
        )

    if product_knowledge_parts:
        sections.append(
            f"## PRODUCT KNOWLEDGE\n" + "\n".join(product_knowledge_parts)
        )

    # Section 4: Compliance Rules
    if ai.compliance_rules:
        sections.append(f"## COMPLIANCE RULES\n{ai.compliance_rules}")

    # Section 5: Conversion Playbook
    if ai.conversion_playbook:
        sections.append(f"## CONVERSION PLAYBOOK\n{ai.conversion_playbook}")

    # Section 5.1: Hardcoded Warrior Babe playbook (TEMP — move to AI Config DB)
    sections.append(_WARRIOR_BABE_PLAYBOOK)

    # Section 6: Objection Handlers
    if ai.objection_handlers:
        handlers_text = json.dumps(ai.objection_handlers, indent=2)
        sections.append(f"## OBJECTION HANDLERS\n{handlers_text}")

    # Section 7: System Prompt Override (takes highest priority)
    if ai.system_prompt_override:
        sections.append(
            f"## ADDITIONAL INSTRUCTIONS\n{ai.system_prompt_override}"
        )

    # Combine all sections into the system prompt text
    full_system_text = "\n\n".join(sections)

    # Return as cache-controlled content blocks for Anthropic SDK.
    # The large system prompt is cached; the response format block is not
    # (it rarely changes but is small).
    return [
        {
            "type": "text",
            "text": full_system_text,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": _RESPONSE_FORMAT_INSTRUCTION,
        },
    ]


# ── Response format instruction ────────────────────────────────

_RESPONSE_FORMAT_INSTRUCTION = """## RESPONSE FORMAT

You MUST respond with valid JSON in the following structure. Do NOT include any text outside the JSON block.

```json
{
  "response_text": "Your conversational response to the customer",
  "buyer_stage": "awareness|consideration|intent|purchase|post_purchase",
  "intent_signals": ["signal1", "signal2"],
  "conversion_ready": false,
  "suggested_quick_replies": ["Option 1", "Option 2"],
  "custom_field_updates": {},
  "compliance_flags": []
}
```

FIELD RULES:
- response_text: Your natural reply. Keep it concise (2-4 sentences for messaging).
- buyer_stage: Your assessment of where this customer is in their journey.
- intent_signals: Key signals you detected (e.g., "asked_about_pricing", "expressed_urgency", "mentioned_competitor").
- conversion_ready: Set to true only if the customer has explicitly expressed intent to purchase.
- suggested_quick_replies: 1-3 suggested reply buttons that guide the conversation (e.g., "Tell me more", "See pricing", "Talk to a human").
- custom_field_updates: Any key-value pairs to track in the customer profile.
- compliance_flags: List any compliance concerns (empty array if none)."""


def build_user_message(context: ConversationContext) -> str:
    """
    Build the user message block from conversation context.

    Includes conversation history (last 10), subscriber profile, and
    the current message.

    Args:
        context: Full conversation context.

    Returns:
        Formatted user message string for Claude.
    """
    parts: list[str] = []

    # Subscriber profile context
    sub = context.subscriber
    profile_parts = [f"Channel: {sub.channel}"]
    if sub.first_name:
        profile_parts.append(f"Name: {sub.first_name} {sub.last_name or ''}".strip())
    profile_parts.append(f"Buyer Stage: {sub.buyer_stage}")
    if sub.interests:
        profile_parts.append(f"Interests: {', '.join(sub.interests)}")
    if sub.objections_raised:
        profile_parts.append(f"Previous Objections: {', '.join(sub.objections_raised)}")
    if sub.conversation_summary:
        profile_parts.append(f"Conversation Summary: {sub.conversation_summary}")
    profile_parts.append(f"Total Messages: {sub.total_messages}")

    parts.append("## SUBSCRIBER PROFILE\n" + "\n".join(profile_parts))

    hyros_section = _build_hyros_profile_section(sub)
    if hyros_section:
        parts.append(hyros_section)

    # Conversation history
    if context.history:
        history_lines: list[str] = []
        for msg in context.history[-10:]:  # Last 10 messages
            role_label = msg.sender.upper()
            history_lines.append(f"[{role_label}]: {msg.content}")

        parts.append(
            "## CONVERSATION HISTORY\n" + "\n".join(history_lines)
        )

    # General knowledge (retrieved from knowledge documents)
    if context.retrieved_knowledge:
        knowledge_text = "\n".join(context.retrieved_knowledge)
        parts.append(f"## GENERAL KNOWLEDGE\n{knowledge_text}")

    # Current message
    parts.append(f"## CURRENT MESSAGE\n[USER]: {context.current_message}")

    return "\n\n".join(parts)
