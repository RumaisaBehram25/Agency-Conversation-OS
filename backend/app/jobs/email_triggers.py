"""
Attora — Email Trigger Jobs

1. reengagement_email_sweep  — daily cron: finds cold subscribers
   (intent/consideration, no activity for org-configured days) and
   queues a re-engagement email.

2. new_product_email_sweep   — called after a product is created:
   finds converted subscribers in the same org and queues a
   new-product notification email.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("attora.jobs.email_triggers")


# ---------------------------------------------------------------------------
# Re-engagement sweep (daily cron)
# ---------------------------------------------------------------------------

async def reengagement_email_sweep(db: AsyncSession) -> dict:
    """
    Queue re-engagement emails for subscribers who have gone cold.

    Eligibility rules (all must pass):
    - org has emails_enabled = true
    - subscriber has a non-null email
    - buyer_stage is 'intent' or 'consideration'
    - last_activity_at is older than org's no_response_followup_days
    - no email already queued (pending/processing) for this subscriber
    - no email sent to this subscriber in the last 30 days
    """
    result = await db.execute(text("""
        SELECT
            s.id            AS subscriber_id,
            s.org_id        AS org_id,
            s.email         AS email,
            oes.no_response_followup_days
        FROM subscribers s
        JOIN organization_email_settings oes
            ON oes.organization_id = s.org_id
        WHERE
            oes.emails_enabled = true
            AND s.email IS NOT NULL
            AND s.buyer_stage IN ('intent', 'consideration')
            AND s.last_activity_at < now() - (oes.no_response_followup_days || ' days')::interval
            AND NOT EXISTS (
                SELECT 1 FROM email_queue eq
                WHERE eq.subscriber_id = s.id
                  AND eq.status IN ('pending', 'processing')
            )
            AND NOT EXISTS (
                SELECT 1 FROM email_log el
                WHERE el.subscriber_id = s.id
                  AND el.status = 'sent'
                  AND el.sent_at > now() - interval '30 days'
            )
    """))

    rows = result.mappings().all()

    if not rows:
        logger.info("reengagement_email_sweep: no eligible subscribers found")
        return {"queued": 0, "message": "No eligible subscribers found"}

    queued = 0
    for row in rows:
        await db.execute(text("""
            INSERT INTO email_queue
                (organization_id, subscriber_id, trigger_type, priority, status)
            VALUES
                (:org_id, :subscriber_id, 'no_response_followup', 10, 'pending')
        """), {
            "org_id": row["org_id"],
            "subscriber_id": row["subscriber_id"],
        })
        queued += 1

    await db.flush()
    logger.info("reengagement_email_sweep: queued %d emails", queued)
    return {"queued": queued, "message": f"Queued {queued} re-engagement emails"}


# ---------------------------------------------------------------------------
# New-product sweep (called from product creation endpoint)
# ---------------------------------------------------------------------------

async def new_product_email_sweep(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    product_id: uuid.UUID,
) -> dict:
    """
    Queue new-product notification emails for converted subscribers in the org.

    Eligibility rules (all must pass):
    - org has emails_enabled = true
    - product is not in org's blocked_product_ids
    - subscriber is converted (is_converted = true) and has email
    - subscriber has not already been emailed about this product
    - subscriber not already queued (pending/processing)
    - subscriber not emailed in the last min_days_between_emails days
    """
    # Check org settings first
    settings_result = await db.execute(text("""
        SELECT
            emails_enabled,
            blocked_product_ids,
            min_days_between_emails
        FROM organization_email_settings
        WHERE organization_id = :org_id
    """), {"org_id": org_id})

    settings_row = settings_result.mappings().first()

    if not settings_row or not settings_row["emails_enabled"]:
        logger.info("new_product_email_sweep: emails disabled for org %s", org_id)
        return {"queued": 0, "message": "Emails disabled for this org"}

    blocked = settings_row["blocked_product_ids"] or []
    if str(product_id) in [str(b) for b in blocked]:
        logger.info("new_product_email_sweep: product %s is blocked for org %s", product_id, org_id)
        return {"queued": 0, "message": "Product is blocked from email"}

    min_days = settings_row["min_days_between_emails"]

    # Find eligible converted subscribers
    result = await db.execute(text("""
        SELECT s.id AS subscriber_id, s.email AS email
        FROM subscribers s
        WHERE
            s.org_id = :org_id
            AND s.email IS NOT NULL
            AND s.is_converted = true
            AND NOT EXISTS (
                SELECT 1 FROM email_log el
                WHERE el.subscriber_id = s.id
                  AND el.product_id = :product_id
                  AND el.status = 'sent'
            )
            AND NOT EXISTS (
                SELECT 1 FROM email_queue eq
                WHERE eq.subscriber_id = s.id
                  AND eq.product_id = :product_id
                  AND eq.status IN ('pending', 'processing')
            )
            AND NOT EXISTS (
                SELECT 1 FROM email_log el2
                WHERE el2.subscriber_id = s.id
                  AND el2.status = 'sent'
                  AND el2.sent_at > now() - (:min_days || ' days')::interval
            )
    """), {
        "org_id": org_id,
        "product_id": product_id,
        "min_days": min_days,
    })

    rows = result.mappings().all()

    if not rows:
        logger.info("new_product_email_sweep: no eligible subscribers for product %s", product_id)
        return {"queued": 0, "message": "No eligible subscribers"}

    queued = 0
    for row in rows:
        await db.execute(text("""
            INSERT INTO email_queue
                (organization_id, subscriber_id, trigger_type, product_id, priority, status)
            VALUES
                (:org_id, :subscriber_id, 'new_product_match', :product_id, 5, 'pending')
        """), {
            "org_id": org_id,
            "subscriber_id": row["subscriber_id"],
            "product_id": product_id,
        })
        queued += 1

    await db.flush()
    logger.info("new_product_email_sweep: queued %d emails for product %s", queued, product_id)
    return {"queued": queued, "message": f"Queued {queued} new-product emails"}