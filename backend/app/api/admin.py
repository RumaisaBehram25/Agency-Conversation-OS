"""
Admin utilities (owner/admin only).

TEMPORARY: ``GET /admin/debug-followup`` — delete after diagnosing follow-up cron.
Protected by ``X-Cron-Secret`` only (no JWT).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cron import verify_cron_secret
from app.api.deps import get_current_user, get_org_id
from app.database import get_db
from app.models.base import ConversationStatus, MessageSender, UserRole
from app.models.campaign import AdCampaign
from app.models.conversation import Conversation
from app.models.follow_up import CampaignFollowUp
from app.models.message import Message
from app.models.organization import Organization
from app.models.subscriber import Subscriber
from app.models.user import OrgUser, User
from app.security.encryption import decrypt_value
from app.services.follow_up_engine import _has_purchased

logger = logging.getLogger(__name__)

router = APIRouter()

DEBUG_ORG_SLUG = "warrior-babe"
SAMPLE_LIMIT = 25


async def _require_org_admin(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(OrgUser).where(OrgUser.user_id == user_id, OrgUser.org_id == org_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None or membership.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Requires owner or admin role.",
        )


@router.post("/reset-follow-ups")
async def reset_follow_ups(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    conversation_id: uuid.UUID | None = Query(None, description="Reset a single conversation"),
    campaign_id: uuid.UUID | None = Query(None, description="Reset all conversations for subscribers on this campaign"),
) -> dict:
    """
    Set follow_up_attempts=0 (and clear last_follow_up_at) for parked or stuck sequences.

    Provide **exactly one** of ``conversation_id`` or ``campaign_id``.
    """
    await _require_org_admin(db, current_user.id, org_id)

    has_conv = conversation_id is not None
    has_camp = campaign_id is not None
    if has_conv == has_camp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide exactly one of conversation_id or campaign_id",
        )

    if conversation_id:
        result = await db.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.org_id == org_id,
            )
            .values(follow_up_attempts=0, last_follow_up_at=None)
        )
        n = result.rowcount or 0
        if n == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found in this organization",
            )
        logger.info(
            "reset_follow_ups: org=%s conversation_id=%s rows=%s by user=%s",
            org_id,
            conversation_id,
            n,
            current_user.id,
        )
    else:
        subscriber_ids = (
            select(Subscriber.id).where(
                Subscriber.org_id == org_id,
                Subscriber.attora_campaign_id == campaign_id,
            )
        )
        result = await db.execute(
            update(Conversation)
            .where(
                Conversation.org_id == org_id,
                Conversation.subscriber_id.in_(subscriber_ids),
            )
            .values(follow_up_attempts=0, last_follow_up_at=None)
        )
        n = result.rowcount or 0
        logger.info(
            "reset_follow_ups: org=%s campaign_id=%s rows=%s by user=%s",
            org_id,
            campaign_id,
            n,
            current_user.id,
        )

    await db.commit()
    return {
        "updated": n,
        "conversation_id": str(conversation_id) if conversation_id else None,
        "campaign_id": str(campaign_id) if campaign_id else None,
    }


async def debug_followup_header(
    x_cron_secret: str | None = Header(None, alias="X-Cron-Secret"),
) -> None:
    """
    Cron secret lookup (TEMPORARY).
    Depends(verify_cron_secret) would require marking the header as required=true
    everywhere; manually validate here for this debug-only route.
    """
    if x_cron_secret is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Cron-Secret header",
        )
    await verify_cron_secret(x_cron_secret=x_cron_secret)


@router.get("/debug-followup")
async def debug_followup_diagnostic(
    _: None = Depends(debug_followup_header),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    **TEMPORARY** — remove after debugging follow-up cron (68 errors).
    Protected by ``X-Cron-Secret`` only. Never exposes full API keys.
    """
    org_result = await db.execute(
        select(Organization).where(Organization.slug == DEBUG_ORG_SLUG)
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization slug={DEBUG_ORG_SLUG!r} not found",
        )

    decrypt_test = "success"
    api_key_preview: str | None = None
    try:
        if org.manychat_api_key:
            plain = decrypt_value(org.manychat_api_key)
            api_key_preview = plain[:10] if len(plain) >= 10 else plain
        else:
            decrypt_test = "skipped: manychat_api_key is null"
    except Exception as e:
        decrypt_test = f"failed: {e!s}"

    subs_with_campaign_rq = await db.execute(
        select(func.count())
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org.id,
            Subscriber.attora_campaign_id.isnot(None),
        )
    )
    subscribers_with_campaign = int(subs_with_campaign_rq.scalar() or 0)

    # Diagnostics: conversations with attempts >= number of touches (assume max 4+ rules).
    seq_complete_rq = await db.execute(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.org_id == org.id,
            Conversation.follow_up_attempts >= 4,
        )
    )
    sequence_complete = int(seq_complete_rq.scalar() or 0)

    active_conv_rq = await db.execute(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.org_id == org.id,
            Conversation.status == ConversationStatus.ACTIVE,
        )
    )
    active_conversations = int(active_conv_rq.scalar() or 0)

    null_lum_rq = await db.execute(
        select(func.count())
        .select_from(Subscriber)
        .where(
            Subscriber.org_id == org.id,
            Subscriber.attora_campaign_id.isnot(None),
            Subscriber.last_user_message_at.is_(None),
        )
    )
    null_last_user_message = int(null_lum_rq.scalar() or 0)

    rule_rows_q = await db.execute(
        select(
            CampaignFollowUp.campaign_id,
            CampaignFollowUp.step_order,
            CampaignFollowUp.after_minutes,
            AdCampaign.name,
        )
        .join(AdCampaign, CampaignFollowUp.campaign_id == AdCampaign.id)
        .where(
            CampaignFollowUp.org_id == org.id,
            CampaignFollowUp.is_active.is_(True),
        )
        .order_by(AdCampaign.name.asc(), CampaignFollowUp.step_order.asc())
    )
    rule_rows = rule_rows_q.all()
    rules_steps: dict[uuid.UUID, list[tuple[int, int]]] = defaultdict(list)
    follow_up_rules: list[dict] = []
    for cid, step, after_min, camp_name in rule_rows:
        rules_steps[cid].append((step, after_min))
        follow_up_rules.append(
            {
                "campaign_id": str(cid),
                "campaign_name": camp_name,
                "step_order": step,
                "after_minutes": after_min,
            }
        )
    after_minutes_by_campaign: dict[uuid.UUID, list[int]] = {}
    rules_len_by_campaign: dict[uuid.UUID, int] = {}
    for cid, pairs in rules_steps.items():
        pairs.sort(key=lambda t: t[0])
        ordered_after = [p[1] for p in pairs]
        after_minutes_by_campaign[cid] = ordered_after
        rules_len_by_campaign[cid] = len(ordered_after)
    active_rule_count = sum(rules_len_by_campaign.values())

    last_sender_rows = await db.execute(
        text(
            """
            SELECT m.sender::text AS sender, COUNT(*)::bigint AS ct
            FROM (
                SELECT DISTINCT ON (conversation_id) conversation_id, sender
                FROM messages
                WHERE conversation_id IN (
                    SELECT id FROM conversations
                    WHERE org_id = CAST(:org_id AS uuid) AND status = 'active'
                )
                ORDER BY conversation_id, created_at DESC
            ) AS m
            GROUP BY m.sender
            """
        ),
        {"org_id": str(org.id)},
    )
    latest_message_sender_counts: dict[str, int] = {
        row[0]: int(row[1]) for row in last_sender_rows.all() if row[0] is not None
    }

    now = datetime.now(timezone.utc)
    subscribers_q = await db.execute(
        select(Subscriber)
        .where(
            Subscriber.org_id == org.id,
            Subscriber.attora_campaign_id.isnot(None),
        )
        .order_by(Subscriber.updated_at.desc().nullslast())
        .limit(SAMPLE_LIMIT)
    )
    sample_subs = list(subscribers_q.scalars().unique().all())
    _campaign_ids = {s.attora_campaign_id for s in sample_subs if s.attora_campaign_id}
    campaign_names: dict[uuid.UUID, str] = {}
    if _campaign_ids:
        campaigns_with_rules_rq = await db.execute(
            select(AdCampaign.id, AdCampaign.name).where(
                AdCampaign.id.in_(_campaign_ids),
                AdCampaign.org_id == org.id,
            )
        )
        campaign_names = dict(campaigns_with_rules_rq.all())

    sample_subscribers_out: list[dict] = []
    for sub in sample_subs:
        conv_rq = await db.execute(
            select(Conversation)
            .where(
                Conversation.subscriber_id == sub.id,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .order_by(Conversation.last_activity_at.desc())
            .limit(1)
        )
        conv = conv_rq.scalar_one_or_none()
        n_rules = (
            rules_len_by_campaign.get(sub.attora_campaign_id, 0)
            if sub.attora_campaign_id
            else 0
        )

        skip_reason = ""
        would_send = False
        last_sender = None
        silence_anchor_iso: str | None = None
        elapsed_minutes: float | None = None

        if _has_purchased(sub):
            skip_reason = "skipped_purchased"
        elif conv is None:
            skip_reason = "skipped_no_active_conversation"
        elif n_rules == 0:
            skip_reason = "skipped_no_follow_up_rules"
        elif conv.follow_up_attempts >= n_rules:
            skip_reason = "skipped_sequence_complete"
        else:
            anchor = (
                sub.last_user_message_at
                or conv.started_at
                or conv.created_at
            )
            if anchor is None:
                skip_reason = "skipped_threshold_not_met (no silence anchor)"
            else:
                if anchor.tzinfo is None:
                    anchor = anchor.replace(tzinfo=timezone.utc)
                silence_anchor_iso = anchor.isoformat()
                elapsed_minutes = max(0.0, (now - anchor).total_seconds() / 60.0)

                lm_rq = await db.execute(
                    select(Message.sender)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                lm = lm_rq.scalar_one_or_none()
                last_sender = getattr(lm, "value", lm) if lm is not None else None

                chain_after = []
                if sub.attora_campaign_id:
                    chain_after = after_minutes_by_campaign.get(sub.attora_campaign_id, [])

                if lm is None or lm not in (MessageSender.AI, MessageSender.HUMAN):
                    skip_reason = (
                        "skipped_engaged (no outbound last message)" if lm is None
                        else f"skipped_engaged last_sender={last_sender}"
                    )
                elif conv.follow_up_attempts >= len(chain_after):
                    skip_reason = "skipped_sequence_complete (no next rule index)"
                elif elapsed_minutes < chain_after[conv.follow_up_attempts]:
                    skip_reason = (
                        f"skipped_threshold_not_met elapsed={elapsed_minutes:.1f}"
                        f" < after_minutes={chain_after[conv.follow_up_attempts]}"
                    )
                else:
                    would_send = True
                    skip_reason = "eligible (cron would attempt ManyChat)"

        sample_subscribers_out.append(
            {
                "manychat_id": sub.manychat_subscriber_id,
                "buyer_stage": getattr(sub.buyer_stage, "value", sub.buyer_stage),
                "hyros_purchased": sub.hyros_purchased,
                "attora_campaign_id": str(sub.attora_campaign_id)
                if sub.attora_campaign_id
                else None,
                "campaign_name": campaign_names.get(sub.attora_campaign_id)
                if sub.attora_campaign_id
                else None,
                "follow_up_attempts": conv.follow_up_attempts if conv else None,
                "conv_status": getattr(conv.status, "value", str(conv.status)) if conv else None,
                "last_sender": last_sender,
                "silence_anchor": silence_anchor_iso,
                "elapsed_minutes": (
                    round(elapsed_minutes, 2) if elapsed_minutes is not None else None
                ),
                "would_send": would_send,
                "skip_reason": skip_reason or "unchecked",
                "conversation_id": str(conv.id) if conv else None,
            }
        )

    return {
        "_remove_after_debug": (
            "Delete GET /api/admin/debug-followup when done; uses X-Cron-Secret only"
        ),
        "decrypt_test": decrypt_test,
        "api_key_preview": api_key_preview,
        "subscribers_with_campaign": subscribers_with_campaign,
        "active_conversations": active_conversations,
        "sequence_complete": sequence_complete,
        "null_last_user_message": null_last_user_message,
        "active_follow_up_rules_count": active_rule_count,
        "conversation_last_sender_counts": latest_message_sender_counts,
        "follow_up_rules": follow_up_rules,
        "sample_subscribers": sample_subscribers_out,
        "_org_id": str(org.id),
        "_manychat_outbound_flow_ns_configured": bool(org.manychat_outbound_flow_ns),
    }
