"""
Attora — Stale Conversations Job

Finds conversations with last_activity_at > 24h ago and status='active',
marks them as 'stale'.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.base import ConversationStatus

logger = logging.getLogger("attora.jobs.stale_conversations")


async def mark_stale_conversations(db: AsyncSession) -> dict:
    """
    Find active conversations with no activity for 24+ hours and mark them stale.

    Returns a summary of how many conversations were marked stale.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    # Find active conversations with last_activity_at older than cutoff
    result = await db.execute(
        select(Conversation.id)
        .where(
            Conversation.status == ConversationStatus.ACTIVE,
            Conversation.last_activity_at < cutoff,
            Conversation.last_activity_at.isnot(None),
        )
    )
    stale_ids = [row[0] for row in result.all()]

    if not stale_ids:
        logger.info("No stale conversations found")
        return {"marked_stale": 0, "message": "No stale conversations found"}

    # Batch update to stale
    await db.execute(
        update(Conversation)
        .where(Conversation.id.in_(stale_ids))
        .values(status=ConversationStatus.STALE)
    )

    await db.flush()

    logger.info(f"Marked {len(stale_ids)} conversations as stale")

    return {
        "marked_stale": len(stale_ids),
        "message": f"Marked {len(stale_ids)} conversations as stale",
    }
