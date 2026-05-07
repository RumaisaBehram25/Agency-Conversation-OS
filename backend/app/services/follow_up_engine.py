"""
Attora — Follow-up Dispatcher

Picks subscribers who have gone silent past a campaign's configured
threshold and pushes the next-due nudge through ManyChat.

Decision flow per subscriber (all must be true):
  1. Silent — `now() - silence_anchor >= rule.after_minutes`,
     where `silence_anchor = COALESCE(last_user_message_at, conv.started_at)`.
  2. Last message was outbound (we don't nudge an actively-engaged thread).
  3. Hasn't bought — `hyros_purchased = false` AND
     `buyer_stage NOT IN (purchase, post_purchase)` AND no recorded
     ConversionEvent of type=purchase.
  4. Hasn't already received this rule — `conv.follow_up_attempts < len(rules)`.

When the user replies inbound (handled in `services/context_manager.py`),
`follow_up_attempts` resets to 0 so a returning lead who goes silent
again gets the full sequence over.

Operational note: **`FOLLOW_UP_PARKED_SENTINEL`** (`99`) is written by
`scripts/park_backlog_except.py` to deliberately skip sequences for bulk
cold leads (`follow_up_attempts >= len(rules)`). Reset with
`backend/scripts/reset_parked_conversations.py`, `POST /api/admin/reset-follow-ups`,
or SQL `UPDATE conversations SET follow_up_attempts = 0, last_follow_up_at = NULL WHERE follow_up_attempts = 99`.

Outbound transport: ManyChat's "open" flow — Attora sets a custom field
`attora_outbound_message` on the subscriber, then triggers the org's
`manychat_outbound_flow_ns`. ManyChat just delivers the field's contents.
Org-level config: `Organization.manychat_outbound_flow_ns`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.messaging.manychat import ManyChatAdapter
from app.models.base import (
    BuyerStage,
    ConversationStatus,
    MessageSender,
)
from app.models.campaign import AdCampaign
from app.models.conversation import Conversation
from app.models.follow_up import CampaignFollowUp
from app.models.message import Message
from app.models.organization import Organization
from app.models.subscriber import Subscriber
from app.security.encryption import decrypt_value
from app.services.ai_engine import _load_subscriber_tagged_urls

logger = logging.getLogger(__name__)

# Intentionally high — `follow_up_attempts >= len(rules)` skips the sequence forever
# unless reset. Scripts/park_backlog_except.py sets this value to park backlog.
FOLLOW_UP_PARKED_SENTINEL = 99


def _sub_label(subscriber: Subscriber) -> str:
    return subscriber.manychat_subscriber_id or str(subscriber.id)


@dataclass
class FollowUpResult:
    orgs_scanned: int = 0
    subscribers_scanned: int = 0
    nudges_sent: int = 0
    skipped_no_outbound_flow: int = 0
    skipped_no_active_conversation: int = 0
    skipped_purchased: int = 0
    skipped_engaged: int = 0
    skipped_threshold_not_met: int = 0
    skipped_sequence_complete: int = 0
    errors: int = 0
    dry_run: bool = False

    def asdict(self) -> dict:
        return {
            "orgs_scanned": self.orgs_scanned,
            "subscribers_scanned": self.subscribers_scanned,
            "nudges_sent": self.nudges_sent,
            "skipped_no_outbound_flow": self.skipped_no_outbound_flow,
            "skipped_no_active_conversation": self.skipped_no_active_conversation,
            "skipped_purchased": self.skipped_purchased,
            "skipped_engaged": self.skipped_engaged,
            "skipped_threshold_not_met": self.skipped_threshold_not_met,
            "skipped_sequence_complete": self.skipped_sequence_complete,
            "errors": self.errors,
            "dry_run": self.dry_run,
        }


def _render_message(template: str, urls: dict[str, str]) -> str:
    """Replace `[LINK]` placeholder with the stamped checkout URL."""
    if "[LINK]" not in template:
        return template
    link = urls.get("checkout") or urls.get("product_page") or urls.get("success") or ""
    return template.replace("[LINK]", link)


def _has_purchased(subscriber: Subscriber) -> bool:
    if subscriber.hyros_purchased:
        return True
    if subscriber.buyer_stage in (BuyerStage.PURCHASE, BuyerStage.POST_PURCHASE):
        return True
    return False


async def _last_message_sender(
    db: AsyncSession, conversation_id: uuid.UUID
) -> MessageSender | None:
    result = await db.execute(
        select(Message.sender)
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _send_via_manychat(
    org: Organization,
    subscriber: Subscriber,
    message: str,
) -> bool:
    """Send follow-up text via ManyChat ``/sending/sendContent``. Returns True on success."""
    if not org.manychat_api_key:
        return False
    try:
        api_key = decrypt_value(org.manychat_api_key)
    except Exception:
        logger.exception(
            "[FOLLOWUP] decrypt_value failed for org manychat_api_key org_id=%s org_slug=%s",
            org.id,
            getattr(org, "slug", None),
        )
        return False

    adapter = ManyChatAdapter(api_key=api_key)
    mc_sub = subscriber.manychat_subscriber_id
    try:
        await adapter.send_message(
            subscriber_id=mc_sub,
            text=message,
        )
    except Exception:
        logger.exception(
            "[FOLLOWUP] ManyChat send_message failed org_id=%s subscriber_id=%s "
            "manychat_subscriber_id=%s",
            org.id,
            subscriber.id,
            mc_sub,
        )
        return False

    return True


async def _process_subscriber(
    db: AsyncSession,
    org: Organization,
    subscriber: Subscriber,
    rules: list[CampaignFollowUp],
    now: datetime,
    result: FollowUpResult,
    *,
    dry_run: bool,
) -> None:
    result.subscribers_scanned += 1
    sub_id = _sub_label(subscriber)

    if _has_purchased(subscriber):
        result.skipped_purchased += 1
        logger.info(
            "[FOLLOWUP] skip=sub=%s reason=skipped_purchased buyer_stage=%s hyros_purchased=%s",
            sub_id,
            getattr(subscriber.buyer_stage, "value", subscriber.buyer_stage),
            subscriber.hyros_purchased,
        )
        return

    # Find an active conversation. There can be more than one for a sub
    # over time; we only nudge on the most recent active one.
    conv_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.subscriber_id == subscriber.id,
            Conversation.status == ConversationStatus.ACTIVE,
        )
        .order_by(desc(Conversation.last_activity_at))
        .limit(1)
    )
    conv = conv_result.scalar_one_or_none()
    if conv is None:
        result.skipped_no_active_conversation += 1
        logger.info(
            "[FOLLOWUP] skip=sub=%s reason=skipped_no_active_conversation",
            sub_id,
        )
        return

    if conv.follow_up_attempts >= len(rules):
        result.skipped_sequence_complete += 1
        logger.info(
            "[FOLLOWUP] skip=sub=%s reason=skipped_sequence_complete conv=%s "
            "follow_up_attempts=%s len(rules)=%s matches_park_sentinel_%s=%s",
            sub_id,
            conv.id,
            conv.follow_up_attempts,
            len(rules),
            FOLLOW_UP_PARKED_SENTINEL,
            conv.follow_up_attempts == FOLLOW_UP_PARKED_SENTINEL,
        )
        return

    next_rule = rules[conv.follow_up_attempts]

    # Anchor the silence timer.
    silence_anchor = subscriber.last_user_message_at or conv.started_at or conv.created_at
    if silence_anchor is None:
        result.skipped_threshold_not_met += 1
        logger.info(
            "[FOLLOWUP] skip=sub=%s reason=skipped_threshold_not_met conv=%s detail=no_silence_anchor",
            sub_id,
            conv.id,
        )
        return

    if silence_anchor.tzinfo is None:
        silence_anchor = silence_anchor.replace(tzinfo=timezone.utc)

    elapsed_minutes = (now - silence_anchor).total_seconds() / 60.0
    if elapsed_minutes < next_rule.after_minutes:
        result.skipped_threshold_not_met += 1
        logger.info(
            "[FOLLOWUP] skip=sub=%s reason=skipped_threshold_not_met conv=%s "
            "elapsed_minutes=%.2f next_rule.after_minutes=%s step_order=%s",
            sub_id,
            conv.id,
            elapsed_minutes,
            next_rule.after_minutes,
            next_rule.step_order,
        )
        return

    # Don't nudge if the user has just replied (race: cron + webhook).
    last_sender = await _last_message_sender(db, conv.id)
    outbound_was_ours = last_sender in (MessageSender.AI, MessageSender.HUMAN)
    if last_sender is None or not outbound_was_ours:
        result.skipped_engaged += 1
        sender_s = getattr(last_sender, "value", last_sender) if last_sender is not None else None
        logger.info(
            "[FOLLOWUP] skip=sub=%s reason=skipped_engaged conv=%s last_sender=%s",
            sub_id,
            conv.id,
            sender_s,
        )
        return

    # Render the message — substitute [LINK] with the per-subscriber stamped
    # checkout URL.
    try:
        urls = await _load_subscriber_tagged_urls(
            db=db,
            org_id=org.id,
            attora_campaign_id=str(subscriber.attora_campaign_id)
            if subscriber.attora_campaign_id
            else None,
            subscriber_id=subscriber.manychat_subscriber_id,
            attora_id=str(subscriber.id),
        )
    except Exception:
        logger.exception(
            "[FOLLOWUP] _load_subscriber_tagged_urls raised org_id=%s subscriber_id=%s "
            "attora_campaign_id=%s manychat_subscriber_id=%s",
            org.id,
            subscriber.id,
            subscriber.attora_campaign_id,
            subscriber.manychat_subscriber_id,
        )
        result.errors += 1
        return

    rendered = _render_message(next_rule.message, urls)

    if dry_run:
        result.nudges_sent += 1
        logger.info(
            "[FOLLOWUP] dry_run=sub=%s conv=%s would_send touch=%s after_minutes=%s "
            "elapsed_minutes=%.2f preview=%.200s",
            sub_id,
            conv.id,
            next_rule.step_order,
            next_rule.after_minutes,
            elapsed_minutes,
            rendered,
        )
        return

    sent = await _send_via_manychat(org, subscriber, rendered)
    if not sent:
        result.errors += 1
        return

    db.add(
        Message(
            conversation_id=conv.id,
            sender=MessageSender.AI,
            content=rendered,
            is_follow_up=True,
        )
    )
    conv.follow_up_attempts += 1
    conv.last_follow_up_at = now
    conv.last_activity_at = now
    subscriber.last_message_at = now
    result.nudges_sent += 1
    logger.info(
        "[FOLLOWUP] org=%s sub=%s campaign=%s touch=%d sent",
        org.id,
        subscriber.manychat_subscriber_id,
        subscriber.attora_campaign_id,
        next_rule.step_order,
    )


async def dispatch_follow_ups(db: AsyncSession, *, dry_run: bool = False) -> dict:
    """
    Top-level entry point — scans all orgs with follow-ups configured and
    fires due nudges. Caller (cron endpoint) is responsible for db.commit()
    unless dry_run is True.

    When dry_run=True, no ManyChat calls and no follow-up DB mutations
    (messages / attempt counters); nudges_sent counts what would have been sent.
    """
    result = FollowUpResult(dry_run=dry_run)
    now = datetime.now(timezone.utc)

    orgs_q = await db.execute(
        select(Organization).where(
            Organization.manychat_api_key.isnot(None),
        )
    )
    orgs = orgs_q.scalars().all()

    for org in orgs:
        result.orgs_scanned += 1

        # Load this org's campaigns with their follow-up rules.
        camps_q = await db.execute(
            select(AdCampaign)
            .where(
                AdCampaign.org_id == org.id,
                AdCampaign.is_active.is_(True),
                AdCampaign.is_attora_managed.is_(True),
            )
            .options(selectinload(AdCampaign.follow_ups))
        )
        campaigns = camps_q.scalars().all()

        for campaign in campaigns:
            rules = [r for r in campaign.follow_ups if r.is_active]
            rules.sort(key=lambda r: r.step_order)
            if not rules:
                continue

            subs_q = await db.execute(
                select(Subscriber).where(
                    Subscriber.org_id == org.id,
                    Subscriber.attora_campaign_id == campaign.id,
                )
            )
            subscribers = subs_q.scalars().all()

            for subscriber in subscribers:
                try:
                    await _process_subscriber(
                        db, org, subscriber, rules, now, result, dry_run=dry_run
                    )
                except Exception:
                    logger.exception(
                        "[FOLLOWUP] Unhandled error in _process_subscriber "
                        "subscriber_id=%s manychat_subscriber_id=%s org_id=%s campaign_id=%s",
                        subscriber.id,
                        subscriber.manychat_subscriber_id,
                        org.id,
                        campaign.id,
                    )
                    result.errors += 1

    return result.asdict()
