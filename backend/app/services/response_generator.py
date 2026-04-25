"""
Attora — Claude Sonnet Response Generator

Generates AI responses using Claude Sonnet (claude-sonnet-4-6) with a
7-second hard timeout. Uses Anthropic prompt caching for the system prompt
to reduce latency and cost.

Budget: 7 seconds max (leaves 3s buffer for the rest of the pipeline).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import anthropic

from app.config import settings
from app.schemas.ai_engine import (
    AIResponse,
    ConversationContext,
    OrgConfig,
    TokenUsage,
)
from app.services.prompt_builder import build_system_prompt, build_user_message

logger = logging.getLogger(__name__)

# Model configuration
_RESPONSE_MODEL = "claude-sonnet-4-6"
_RESPONSE_TIMEOUT_SECONDS = 12.0  # 12s hard timeout
_MAX_TOKENS = 1024

# Reused across requests. A fresh AsyncAnthropic per call rebuilds the
# underlying HTTPX client and pays TCP/TLS handshake latency every time
# (easily 100-300ms). Instantiating once keeps the HTTP/2 connection warm.
_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def generate_response(
    context: ConversationContext,
    org_config: OrgConfig,
) -> AIResponse:
    """
    Generate an AI response using Claude Sonnet.

    Builds the system prompt from org config, constructs the user message
    from conversation context, and calls Claude with a 7-second timeout.

    Args:
        context: Full conversation context (subscriber, history, current message).
        org_config: Cached organization config (AI settings, products).

    Returns:
        AIResponse with response text, buyer stage, intent signals, etc.

    Raises:
        asyncio.TimeoutError: If the response takes longer than 7 seconds.
    """
    start_time = time.monotonic()

    # Build prompts — pass per-subscriber attribution URLs so the AI
    # quotes attora_sub-tagged links. Identity params (attora_sub, attora_id)
    # get stamped onto product-specific URLs inline.
    system_blocks = build_system_prompt(
        org_config,
        subscriber_urls=context.subscriber_tagged_urls,
        subscriber_id=context.subscriber.subscriber_id,
        attora_id=context.subscriber.attora_id,
    )
    user_message = build_user_message(context)

    try:
        result = await asyncio.wait_for(
            _call_sonnet(system_blocks, user_message),
            timeout=_RESPONSE_TIMEOUT_SECONDS,
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        result.response_time_ms = elapsed_ms
        logger.info(
            f"Sonnet response generated in {elapsed_ms}ms "
            f"(tokens={result.tokens_used}, model={result.model_used})"
        )
        return result

    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.warning(f"Sonnet response timeout after {elapsed_ms}ms")
        raise

    except anthropic.APIError as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(f"Anthropic API error after {elapsed_ms}ms: {e}")
        raise

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(f"Response generation error after {elapsed_ms}ms: {e}")
        raise


async def _call_sonnet(
    system_blocks: list[dict],
    user_message: str,
) -> AIResponse:
    """Make the actual API call to Claude Sonnet."""
    client = _get_client()

    response = await client.messages.create(
        model=_RESPONSE_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_blocks,
        messages=[{"role": "user", "content": user_message}],
    )

    usage = _extract_usage(response)
    tokens_used = usage.input_tokens + usage.output_tokens

    # Parse JSON from response
    raw_text = response.content[0].text.strip()
    parsed = _parse_response_json(raw_text)

    return AIResponse(
        response_text=parsed.get("response_text", raw_text),
        buyer_stage=parsed.get("buyer_stage", "awareness"),
        intent_signals=parsed.get("intent_signals", []),
        conversion_ready=parsed.get("conversion_ready", False),
        suggested_quick_replies=parsed.get("suggested_quick_replies", []),
        custom_field_updates=parsed.get("custom_field_updates", {}),
        compliance_flags=parsed.get("compliance_flags", []),
        model_used=_RESPONSE_MODEL,
        tokens_used=tokens_used,
        usage=usage,
    )


def _extract_usage(response) -> TokenUsage:
    u = getattr(response, "usage", None)
    if u is None:
        return TokenUsage(model=_RESPONSE_MODEL)
    return TokenUsage(
        model=_RESPONSE_MODEL,
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


def _parse_response_json(raw_text: str) -> dict:
    """
    Parse JSON from Claude's response, handling various formats.

    Claude may return:
    - Pure JSON
    - JSON wrapped in ```json ... ``` code blocks
    - JSON with leading/trailing text

    Falls back to treating the entire response as response_text.
    """
    text = raw_text.strip()

    # Try direct JSON parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    if "```" in text:
        try:
            # Find JSON between code fences
            start = text.index("```")
            # Skip the opening fence line
            start = text.index("\n", start) + 1
            end = text.index("```", start)
            json_text = text[start:end].strip()
            return json.loads(json_text)
        except (ValueError, json.JSONDecodeError):
            pass

    # Try finding JSON object in the text
    try:
        brace_start = text.index("{")
        brace_end = text.rindex("}") + 1
        json_text = text[brace_start:brace_end]
        return json.loads(json_text)
    except (ValueError, json.JSONDecodeError):
        pass

    # Last resort: treat entire response as response_text
    logger.warning(f"Could not parse Sonnet JSON response, using raw text: {text[:200]}")
    return {"response_text": text}
