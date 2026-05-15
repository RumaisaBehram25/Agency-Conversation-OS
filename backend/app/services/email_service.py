"""
Outbound transactional email helpers (Resend + org-level safety rails).

Uses SQLAlchemy AsyncSession (same as the rest of the app), not raw asyncpg.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

import resend
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings

logger = logging.getLogger(__name__)


def _default_resend_api_key() -> str | None:
    v = (app_settings.resend_api_key or "").strip()
    if v:
        return v
    env = os.getenv("RESEND_API_KEY")
    return env.strip() if env else None


def _normalize_uuid_list(raw: object) -> list[str]:
    """JSONB blocked_product_ids may be UUIDs or strings."""
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if item is None:
            continue
        out.append(str(item))
    return out


async def can_send_email(
    db: AsyncSession,
    org_id: uuid.UUID,
    subscriber_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
) -> tuple[bool, str | None]:
    row = (
        await db.execute(
            text(
                "SELECT * FROM organization_email_settings "
                "WHERE organization_id = :organization_id"
            ),
            {"organization_id": org_id},
        )
    ).mappings().first()

    if row is None or not row["emails_enabled"]:
        return False, "org_disabled"

    blocked = _normalize_uuid_list(row["blocked_product_ids"])
    if product_id is not None and str(product_id) in blocked:
        return False, "product_blocked"

    last_sent = (
        await db.execute(
            text(
                """
                SELECT sent_at FROM email_log
                WHERE subscriber_id = :subscriber_id
                  AND organization_id = :organization_id
                  AND status = 'sent'
                ORDER BY sent_at DESC
                LIMIT 1
                """
            ),
            {"subscriber_id": subscriber_id, "organization_id": org_id},
        )
    ).mappings().first()

    if last_sent and last_sent["sent_at"] is not None:
        days_since = (datetime.now(timezone.utc) - last_sent["sent_at"]).days
        if days_since < int(row["min_days_between_emails"]):
            return False, "cooldown"

    month_count = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) FROM email_log
                WHERE subscriber_id = :subscriber_id
                  AND organization_id = :organization_id
                  AND status = 'sent'
                  AND sent_at > now() - interval '30 days'
                """
            ),
            {"subscriber_id": subscriber_id, "organization_id": org_id},
        )
    ).scalar_one()

    if int(month_count) >= int(row["max_emails_per_user_per_month"]):
        return False, "rate_limit"

    return True, None


async def send_email(
    db: AsyncSession,
    org_id: uuid.UUID,
    subscriber_id: uuid.UUID,
    to_email: str,
    subject: str,
    html: str,
    trigger_type: str,
    product_id: uuid.UUID | None = None,
) -> dict:
    ok, reason = await can_send_email(db, org_id, subscriber_id, product_id)

    settings_row = (
        await db.execute(
            text(
                "SELECT * FROM organization_email_settings "
                "WHERE organization_id = :organization_id"
            ),
            {"organization_id": org_id},
        )
    ).mappings().first()

    if not ok:
        await db.execute(
            text(
                """
                INSERT INTO email_log
                  (organization_id, subscriber_id, trigger_type,
                   product_id, status, suppression_reason, subject)
                VALUES (:organization_id, :subscriber_id, :trigger_type,
                        :product_id, 'suppressed', :reason, :subject)
                """
            ),
            {
                "organization_id": org_id,
                "subscriber_id": subscriber_id,
                "trigger_type": trigger_type,
                "product_id": product_id,
                "reason": reason,
                "subject": subject,
            },
        )
        return {"status": "suppressed", "reason": reason}

    if settings_row is None:
        await db.execute(
            text(
                """
                INSERT INTO email_log
                  (organization_id, subscriber_id, trigger_type,
                   product_id, status, suppression_reason, subject)
                VALUES (:organization_id, :subscriber_id, :trigger_type,
                        :product_id, 'suppressed', :reason, :subject)
                """
            ),
            {
                "organization_id": org_id,
                "subscriber_id": subscriber_id,
                "trigger_type": trigger_type,
                "product_id": product_id,
                "reason": "no_settings",
                "subject": subject,
            },
        )
        return {"status": "suppressed", "reason": "no_settings"}

    from_name = settings_row.get("from_name") or ""
    from_email = settings_row.get("from_email") or ""
    if not from_email:
        await db.execute(
            text(
                """
                INSERT INTO email_log
                  (organization_id, subscriber_id, trigger_type,
                   product_id, status, suppression_reason, subject)
                VALUES (:organization_id, :subscriber_id, :trigger_type,
                        :product_id, 'suppressed', :reason, :subject)
                """
            ),
            {
                "organization_id": org_id,
                "subscriber_id": subscriber_id,
                "trigger_type": trigger_type,
                "product_id": product_id,
                "reason": "missing_from_email",
                "subject": subject,
            },
        )
        return {"status": "suppressed", "reason": "missing_from_email"}

    api_key = (settings_row.get("resend_api_key") or "").strip() or _default_resend_api_key()
    if not api_key:
        await db.execute(
            text(
                """
                INSERT INTO email_log
                  (organization_id, subscriber_id, trigger_type,
                   product_id, status, suppression_reason, subject)
                VALUES (:organization_id, :subscriber_id, :trigger_type,
                        :product_id, 'suppressed', :reason, :subject)
                """
            ),
            {
                "organization_id": org_id,
                "subscriber_id": subscriber_id,
                "trigger_type": trigger_type,
                "product_id": product_id,
                "reason": "missing_resend_key",
                "subject": subject,
            },
        )
        return {"status": "suppressed", "reason": "missing_resend_key"}

    resend.api_key = api_key

    payload: dict = {
        "from": f"{from_name} <{from_email}>" if from_name else from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    reply_to = settings_row.get("reply_to")
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        response = resend.Emails.send(payload)
        rid = response.get("id") if isinstance(response, dict) else None
        if not rid:
            logger.error("Resend returned unexpected payload: %r", response)
            raise RuntimeError("Resend did not return a message id")

        await db.execute(
            text(
                """
                INSERT INTO email_log
                  (organization_id, subscriber_id, trigger_type, product_id,
                   status, resend_message_id, subject, sent_at)
                VALUES (:organization_id, :subscriber_id, :trigger_type,
                        :product_id, 'sent', :resend_message_id, :subject,
                        now())
                """
            ),
            {
                "organization_id": org_id,
                "subscriber_id": subscriber_id,
                "trigger_type": trigger_type,
                "product_id": product_id,
                "resend_message_id": rid,
                "subject": subject,
            },
        )
        return {"status": "sent", "resend_id": rid}

    except Exception as exc:
        logger.exception("Resend send failed for org=%s sub=%s", org_id, subscriber_id)
        await db.execute(
            text(
                """
                INSERT INTO email_log
                  (organization_id, subscriber_id, trigger_type,
                   product_id, status, subject)
                VALUES (:organization_id, :subscriber_id, :trigger_type,
                        :product_id, 'failed', :subject)
                """
            ),
            {
                "organization_id": org_id,
                "subscriber_id": subscriber_id,
                "trigger_type": trigger_type,
                "product_id": product_id,
                "subject": subject,
            },
        )
        # Do not re-raise: avoid rolling back logged failure rows in get_db.
        return {"status": "failed", "error": str(exc)}
