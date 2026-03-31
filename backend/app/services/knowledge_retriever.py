"""
Attora — Knowledge Retriever

Retrieves relevant sales knowledge documents from the knowledge_documents
table using Haiku-generated keyword matching. Provides context to the
AI response generator for better objection handling and sales techniques.

Pipeline: generate_search_keywords -> search_knowledge -> summarize_knowledge
Total budget: ~1 second. Gracefully degrades on any failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.knowledge_document import KnowledgeDocument

logger = logging.getLogger(__name__)

# Model configuration
_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_KEYWORD_TIMEOUT_SECONDS = 0.5
_SUMMARIZE_TIMEOUT_SECONDS = 0.5
_MAX_TOKENS = 256
_MAX_DOCUMENTS = 5

# System prompts
_KEYWORD_SYSTEM_PROMPT = (
    "You are a keyword extractor. Given a sales conversation message and buyer "
    "stage, output a JSON array of 3-7 keyword tags that would match relevant "
    "sales knowledge documents. Focus on: objection type, buyer concern, sales "
    "technique needed, emotional state. Only output the JSON array, nothing else."
)

_SUMMARIZE_SYSTEM_PROMPT = (
    "You are a sales knowledge synthesizer. Given retrieved sales knowledge "
    "documents and a customer message, create a concise 2-4 sentence summary "
    "of the most relevant sales techniques, objection-handling strategies, and "
    "talking points. Focus on actionable advice the AI sales assistant should "
    "apply. Only output the summary, nothing else."
)

# Fallback keywords by buyer stage
_STAGE_FALLBACK_KEYWORDS: dict[str, list[str]] = {
    "awareness": ["overview", "introduction", "benefits"],
    "consideration": ["comparison", "features", "value"],
    "intent": ["pricing", "checkout", "purchase"],
    "purchase": ["confirmation", "onboarding", "next_steps"],
    "post_purchase": ["support", "follow_up", "retention"],
    "objection": ["objection", "technique", "reframe"],
}


async def retrieve_knowledge(
    message: str,
    buyer_stage: str,
    db: AsyncSession,
) -> list[str]:
    """
    Orchestrator: generate keywords, search documents, summarize results.

    Returns a list with the summary string, or an empty list if anything fails.
    This is the entry point called by ai_engine.py.

    Args:
        message: The current user message.
        buyer_stage: Current buyer stage string.
        db: Async database session.

    Returns:
        List containing the knowledge summary, or empty list on failure.
    """
    start_time = time.monotonic()

    try:
        # Step 1: Generate search keywords
        keywords = await generate_search_keywords(message, buyer_stage)
        if not keywords:
            logger.debug("No keywords generated, skipping knowledge retrieval")
            return []

        # Step 2: Search knowledge documents
        documents = await search_knowledge(keywords, db)
        if not documents:
            logger.debug("No knowledge documents found for keywords: %s", keywords)
            return []

        # Step 3: Summarize retrieved documents
        summary = await summarize_knowledge(documents, message)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.debug(
            f"Knowledge retrieval completed in {elapsed_ms}ms "
            f"(keywords={keywords}, docs={len(documents)})"
        )

        return [summary] if summary else []

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(
            f"Knowledge retrieval failed after {elapsed_ms}ms: {e}",
            exc_info=True,
        )
        return []


async def generate_search_keywords(
    message: str,
    buyer_stage: str,
) -> list[str]:
    """
    Use Haiku to generate keyword tags from the conversation message.

    Args:
        message: The current user message.
        buyer_stage: Current buyer stage string.

    Returns:
        List of keyword strings for document matching.
    """
    user_content = (
        f"Buyer stage: {buyer_stage}\n\n"
        f"Customer message: {message}"
    )

    try:
        result = await asyncio.wait_for(
            _call_haiku(
                system_prompt=_KEYWORD_SYSTEM_PROMPT,
                user_content=user_content,
            ),
            timeout=_KEYWORD_TIMEOUT_SECONDS,
        )

        # Parse JSON array from response
        raw_text = result.strip()
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            raw_text = "\n".join(lines[1:-1]) if len(lines) > 2 else raw_text

        keywords = json.loads(raw_text)
        if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
            return keywords[:7]

        logger.warning(f"Keyword extractor returned unexpected format: {raw_text[:200]}")
        return _fallback_keywords(buyer_stage)

    except asyncio.TimeoutError:
        logger.warning("Keyword generation timed out, using fallback")
        return _fallback_keywords(buyer_stage)

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Keyword generation failed: {e}, using fallback")
        return _fallback_keywords(buyer_stage)


async def search_knowledge(
    keywords: list[str],
    db: AsyncSession,
) -> list[dict]:
    """
    Query knowledge_documents where keywords overlap with generated keywords.

    Args:
        keywords: List of keyword strings to match against.
        db: Async database session.

    Returns:
        List of dicts with title, content, section_name, keywords.
    """
    try:
        stmt = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.is_active.is_(True),
                KnowledgeDocument.keywords.overlap(keywords),
            )
            .limit(_MAX_DOCUMENTS)
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        return [
            {
                "title": doc.title,
                "content": doc.content,
                "section_name": doc.section_name,
                "keywords": doc.keywords,
            }
            for doc in documents
        ]

    except Exception as e:
        logger.error(f"Knowledge document search failed: {e}", exc_info=True)
        return []


async def summarize_knowledge(
    documents: list[dict],
    message: str,
) -> str:
    """
    Use Haiku to summarize retrieved documents into actionable context.

    Args:
        documents: List of document dicts from search_knowledge.
        message: The current user message.

    Returns:
        Concise summary string, or concatenated titles as fallback.
    """
    # Build document context for summarization
    doc_text_parts: list[str] = []
    for doc in documents:
        part = f"### {doc['title']}"
        if doc.get("section_name"):
            part += f" ({doc['section_name']})"
        part += f"\n{doc['content']}"
        doc_text_parts.append(part)

    docs_text = "\n\n".join(doc_text_parts)
    user_content = (
        f"Customer message: {message}\n\n"
        f"Retrieved knowledge documents:\n{docs_text}"
    )

    try:
        result = await asyncio.wait_for(
            _call_haiku(
                system_prompt=_SUMMARIZE_SYSTEM_PROMPT,
                user_content=user_content,
            ),
            timeout=_SUMMARIZE_TIMEOUT_SECONDS,
        )
        return result.strip()

    except asyncio.TimeoutError:
        logger.warning("Knowledge summarization timed out, using title fallback")
        return _fallback_summary(documents)

    except Exception as e:
        logger.warning(f"Knowledge summarization failed: {e}, using title fallback")
        return _fallback_summary(documents)


async def _call_haiku(
    system_prompt: str,
    user_content: str,
) -> str:
    """Make an API call to Claude Haiku. Returns the raw response text."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=_HAIKU_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    return response.content[0].text


def _fallback_keywords(buyer_stage: str) -> list[str]:
    """Return fallback keywords based on buyer stage."""
    return _STAGE_FALLBACK_KEYWORDS.get(buyer_stage, ["general", "sales", "technique"])


def _fallback_summary(documents: list[dict]) -> str:
    """Return a basic fallback summary from document titles."""
    titles = [doc["title"] for doc in documents]
    return "Relevant knowledge: " + "; ".join(titles)
