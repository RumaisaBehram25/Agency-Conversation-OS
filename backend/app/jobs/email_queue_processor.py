"""
Attora — Email Queue Processor

Reads pending rows from email_queue, generates email content via the
email_service, sends via Resend, and marks rows done/failed.

Runs on the same APScheduler as follow-up dispatch (every N minutes).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email_service import send_email

logger = logging.getLogger("attora.jobs.email_queue_processor")

# Max rows to process per run (prevents long-running jobs)
BATCH_SIZE = 50


def _build_email_content(row: dict) -> tuple[str, str]:
    """
    Generate subject + HTML for a queued email based on trigger_type.
    Extend this function as you add more trigger types.
    """
    trigger = row["trigger_type"]

    if trigger == "no_response_followup":
        subject = "Still thinking it over?"
        html = """
        <p>Hey! We noticed it's been a little while since we last connected.</p>
        <p>We'd love to help you take the next step. Reply to this email or
        jump back into the conversation anytime.</p>
        <p>— The Team</p>
        """

    elif trigger == "new_product_match":
        product_name = row.get("product_name") or "something new"
        subject = f"We think you'll love this: {product_name}"
        html = f"""
        <p>Based on what you've purchased before, we think you'll love
        <strong>{product_name}</strong>.</p>
        <p>Check it out and let us know if you have any questions!</p>
        <p>— The Team</p>
        """

    else:
        subject = "A message from us"
        html = "<p>We wanted to reach out. Reply anytime!</p>"

    return subject, html


async def process_email_queue(db: AsyncSession) -> dict:
    """
    Process up to BATCH_SIZE pending email_queue rows.

    For each row:
    1. Mark as 'processing'
    2. Fetch subscriber email + org settings
    3. Generate content
    4. Call send_email (handles guard checks + Resend + logs to email_log)
    5. Mark row 'done' or 'failed'
    """
    # Grab a batch of pending rows
    result = await db.execute(text("""
        SELECT
            eq.id,
            eq.organization_id,
            eq.subscriber_id,
            eq.trigger_type,
            eq.product_id,
            eq.attempts,
            eq.max_attempts,
            s.email         AS to_email,
            p.name          AS product_name
        FROM email_queue eq
        JOIN subscribers s ON s.id = eq.subscriber_id
        LEFT JOIN products p ON p.id = eq.product_id
        WHERE eq.status = 'pending'
          AND eq.scheduled_for <= now()
          AND eq.attempts < eq.max_attempts
        ORDER BY eq.priority ASC, eq.scheduled_for ASC
        LIMIT :batch_size
    """), {"batch_size": BATCH_SIZE})

    rows = result.mappings().all()

    if not rows:
        logger.info("email_queue_processor: nothing to process")
        return {"processed": 0, "sent": 0, "failed": 0, "suppressed": 0}

    # Mark all as processing atomically
    row_ids = [str(r["id"]) for r in rows]
    await db.execute(text("""
        UPDATE email_queue
        SET status = 'processing', attempts = attempts + 1, updated_at = now()
        WHERE id = ANY(:ids::uuid[])
    """), {"ids": row_ids})
    await db.flush()

    sent = failed = suppressed = 0

    for row in rows:
        if not row["to_email"]:
            # No email address — suppress silently
            await db.execute(text("""
                UPDATE email_queue
                SET status = 'suppressed', updated_at = now()
                WHERE id = :id
            """), {"id": str(row["id"])})
            suppressed += 1
            continue

        try:
            subject, html = _build_email_content(dict(row))

            outcome = await send_email(
                db=db,
                org_id=str(row["organization_id"]),
                subscriber_id=str(row["subscriber_id"]),
                to_email=row["to_email"],
                subject=subject,
                html=html,
                trigger_type=row["trigger_type"],
                product_id=str(row["product_id"]) if row["product_id"] else None,
            )

            status = outcome.get("status", "failed")

            if status == "sent":
                sent += 1
            elif status == "suppressed":
                suppressed += 1
            else:
                failed += 1

            queue_status = "done" if status in ("sent", "suppressed") else "failed"

            await db.execute(text("""
                UPDATE email_queue
                SET status = :status, updated_at = now()
                WHERE id = :id
            """), {"status": queue_status, "id": str(row["id"])})

        except Exception as exc:
            logger.exception("email_queue_processor: error processing row %s: %s", row["id"], exc)
            failed += 1
            await db.execute(text("""
                UPDATE email_queue
                SET status = 'failed', last_error = :error, updated_at = now()
                WHERE id = :id
            """), {"error": str(exc)[:500], "id": str(row["id"])})

    await db.flush()

    logger.info(
        "email_queue_processor: processed=%d sent=%d suppressed=%d failed=%d",
        len(rows), sent, suppressed, failed,
    )
    return {
        "processed": len(rows),
        "sent": sent,
        "suppressed": suppressed,
        "failed": failed,
    }