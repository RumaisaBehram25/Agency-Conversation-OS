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

logger = logging.getLogger(__name__)


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


def build_system_prompt(
    org_config: OrgConfig,
) -> list[dict]:
    """
    Build the system prompt as a list of content blocks for Claude.

    Uses Anthropic prompt caching by marking the system prompt sections
    with cache_control. Returns a list of content blocks suitable for
    the anthropic SDK's system parameter.

    Args:
        org_config: Cached organization configuration.

    Returns:
        List of content block dicts for Claude's system parameter.
    """
    sections: list[str] = []

    # Section 1: Base Persona
    sections.append(f"## BASE PERSONA\n{_BASE_PERSONA}")

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

    if org_config.products:
        product_knowledge_parts.append("\n### PRODUCT CATALOG:")
        for p in org_config.products:
            entry = f"- **{p.name}**"
            if p.price is not None:
                entry += f" — {p.currency} {p.price:.2f}"
            if p.description:
                entry += f"\n  {p.description}"
            if p.checkout_url:
                entry += f"\n  Checkout: {p.checkout_url}"
            if p.eligibility_criteria:
                entry += f"\n  Eligibility: {json.dumps(p.eligibility_criteria)}"
            product_knowledge_parts.append(entry)

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
