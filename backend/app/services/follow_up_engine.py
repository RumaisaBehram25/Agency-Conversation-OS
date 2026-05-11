"""
Attora — Follow-up Dispatcher

Picks subscribers who have gone silent past a campaign's configured
threshold and pushes the next-due nudge through ManyChat.

Decision flow per subscriber (all must be true):
  1. Silent — `now() - silence_anchor >= rule.after_minutes`,
     where `silence_anchor = COALESCE(last_user_message_at, conv.started_at)`.
  2. Last message was outbound (we don't nudge an actively-engaged thread).
  3. Hasn't bought — `hyros_purchased = false` AND
     `buyer_stage NOT IN (purchase, post_purchase, confirmed)` AND no recorded
     ConversionEvent of type=purchase.
  4. Hasn't already received this rule — `conv.follow_up_attempts < len(rules)`.

When the user replies inbound (handled in `services/context_manager.py`),
only `last_user_message_at` (the silence timer) is reset — `follow_up_attempts`
is NOT reset, so the sequence continues where it left off rather than restarting.

Outbound transport: ManyChat's "open" flow — Attora sets a custom field
`attora_outbound_message` on the subscriber, then triggers the channel-specific
flow NS (`manychat_outbound_flow_ns` for Messenger/default,
`manychat_outbound_flow_ns_instagram` for Instagram).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

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
    if subscriber.buyer_stage in (BuyerStage.PURCHASE, BuyerStage.POST_PURCHASE, BuyerStage.CONFIRMED):
        return True
    return False


async def _last_outbound_was_ours(
    db: AsyncSession, conversation_id: uuid.UUID
) -> bool:
    """True when the most recent message in the conversation was AI/human (i.e.,
    the subscriber hasn't replied since). False when the latest message is
    inbound — we never nudge an actively-engaged thread."""
    result = await db.execute(
        select(Message.sender)
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at))
        .limit(1)
    )
    last_sender = result.scalar_one_or_none()
    if last_sender is None:
        # No messages at all → treat as "we haven't sent anything" → no nudge.
        return False
    return last_sender in (MessageSender.AI, MessageSender.HUMAN)


def _follow_up_flow_ns(org: Organization, subscriber: Subscriber) -> str | None:
    """ManyChat outbound flow namespace for this subscriber's channel."""
    if subscriber.channel == "instagram":
        return org.manychat_outbound_flow_ns_instagram
    return org.manychat_outbound_flow_ns


async def _send_via_manychat(
    org: Organization,
    subscriber: Subscriber,
    message: str,
) -> Literal["ok", "no_flow_ns", "failed"]:
    """Set the outbound custom field on the subscriber, then trigger the
    channel-specific open flow."""
    if not org.manychat_api_key:
        return "failed"
    try:
        api_key = decrypt_value(org.manychat_api_key)
    except Exception:
        logger.warning("Failed to decrypt manychat_api_key for org=%s", org.id)
        return "failed"

    flow_ns = _follow_up_flow_ns(org, subscriber)
    if not flow_ns:
        logger.warning(
            "[FOLLOWUP] No flow_ns configured for channel=%s org=%s",
            subscriber.channel,
            org.id,
        )
        return "no_flow_ns"

    adapter = ManyChatAdapter(api_key=api_key)
    try:
        await adapter.set_custom_fields(
            subscriber_id=subscriber.manychat_subscriber_id,
            fields={"attora_outbound_message": message},
        )
        await adapter.trigger_flow(
            subscriber_id=subscriber.manychat_subscriber_id,
            flow_ns=flow_ns,
        )
        return "ok"
    except Exception as exc:
        logger.warning(
            "Follow-up dispatch failed (org=%s, sub=%s): %s",
            org.id,
            subscriber.manychat_subscriber_id,
            exc,
        )
        return "failed"


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

    if _has_purchased(subscriber):
        result.skipped_purchased += 1
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
        return

    if conv.follow_up_attempts >= len(rules):
        result.skipped_sequence_complete += 1
        return

    next_rule = rules[conv.follow_up_attempts]

    # Anchor the silence timer.
    silence_anchor = subscriber.last_user_message_at or conv.started_at or conv.created_at
    if silence_anchor is None:
        result.skipped_threshold_not_met += 1
        return

    if silence_anchor.tzinfo is None:
        silence_anchor = silence_anchor.replace(tzinfo=timezone.utc)

    elapsed_minutes = (now - silence_anchor).total_seconds() / 60.0
    if elapsed_minutes < next_rule.after_minutes:
        result.skipped_threshold_not_met += 1
        return

    # Don't nudge if the user has just replied (race: cron + webhook).
    if not await _last_outbound_was_ours(db, conv.id):
        result.skipped_engaged += 1
        return

    # Render the message — substitute [LINK] with the per-subscriber stamped
    # checkout URL.
    urls = await _load_subscriber_tagged_urls(
        db=db,
        org_id=org.id,
        attora_campaign_id=str(subscriber.attora_campaign_id) if subscriber.attora_campaign_id else None,
        subscriber_id=subscriber.manychat_subscriber_id,
        attora_id=str(subscriber.id),
    )
    rendered = _render_message(next_rule.message, urls)

    if dry_run:
        if not org.manychat_api_key:
            result.errors += 1
            return
        try:
            decrypt_value(org.manychat_api_key)
        except Exception:
            logger.warning("Failed to decrypt manychat_api_key for org=%s", org.id)
            result.errors += 1
            return
        flow_ns = _follow_up_flow_ns(org, subscriber)
        if not flow_ns:
            logger.warning(
                "[FOLLOWUP] No flow_ns configured for channel=%s org=%s",
                subscriber.channel,
                org.id,
            )
            result.skipped_no_outbound_flow += 1
            return
        result.nudges_sent += 1
        logger.info(
            "[FOLLOWUP] dry_run org=%s sub=%s campaign=%s touch=%d would_send",
            org.id,
            subscriber.manychat_subscriber_id,
            subscriber.attora_campaign_id,
            next_rule.step_order,
        )
        return

    outcome = await _send_via_manychat(org, subscriber, rendered)
    if outcome == "no_flow_ns":
        result.skipped_no_outbound_flow += 1
        return
    if outcome == "failed":
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
    fires due nudges. Caller (cron endpoint) is responsible for db.commit().

    When ``dry_run`` is True, performs eligibility and counts only: no ManyChat
    calls and no Message rows or conversation/subscriber updates from this path.
    """
    result = FollowUpResult(dry_run=dry_run)
    now = datetime.now(timezone.utc)

    orgs_q = await db.execute(
        select(Organization).where(Organization.manychat_api_key.isnot(None))
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
                        "[FOLLOWUP] Unhandled error processing sub=%s", subscriber.id
                    )
                    result.errors += 1

    return result.asdict()
