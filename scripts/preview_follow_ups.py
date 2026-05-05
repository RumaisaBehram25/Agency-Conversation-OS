"""
Dry-run preview of the follow-up dispatcher.

Mirrors timing and silence logic from ``services.follow_up_engine`` (Touch 1 =
minutes since user / conv start; Touches 2+ = minutes since ``last_follow_up_at``)
but only reads the DB — no ManyChat calls and no writes.

Usage:
    python scripts/preview_follow_ups.py [--org-slug warrior-babe]

Output: one line per eligible subscriber, plus a summary block.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)


def _asyncpg_url() -> str:
    raw = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC") or ""
    if not raw:
        root_env = PROJECT_ROOT / ".env"
        back_env = PROJECT_ROOT / "backend" / ".env"
        print(
            "ERROR: DATABASE_URL or DATABASE_URL_SYNC is not set.",
            file=sys.stderr,
        )
        print(
            f"  Add it to {root_env} and/or {back_env} (see .env.example at repo root).",
            file=sys.stderr,
        )
        sys.exit(1)
    return raw.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres+asyncpg://", "postgres://"
    )


_PURCHASE_STAGES = ("purchase", "post_purchase")


async def _preview(org_slug: str | None) -> None:
    import asyncpg

    conn = await asyncpg.connect(_asyncpg_url())
    try:
        # Orgs eligible — must have an outbound flow configured.
        org_filter = "AND o.slug = $1" if org_slug else ""
        params = [org_slug] if org_slug else []
        orgs = await conn.fetch(
            f"""
            SELECT o.id, o.slug, o.name, o.manychat_outbound_flow_ns
            FROM organizations o
            WHERE o.manychat_api_key IS NOT NULL
              AND o.manychat_outbound_flow_ns IS NOT NULL
              {org_filter}
            ORDER BY o.slug
            """,
            *params,
        )

        if not orgs:
            print("No orgs with manychat_outbound_flow_ns set. Nothing to preview.")
            return

        now = datetime.now(timezone.utc)
        grand_eligible = 0
        grand_scanned = 0
        skip_no_conv = 0
        skip_purchased = 0
        skip_engaged = 0
        skip_threshold = 0
        skip_sequence_done = 0

        for org in orgs:
            print(f"\n=== ORG: {org['slug']} ({org['name']}) ===")
            print(f"    outbound flow: {org['manychat_outbound_flow_ns']}")

            campaigns = await conn.fetch(
                """
                SELECT c.id, c.name, c.keyword, c.source_type
                FROM ad_campaigns c
                WHERE c.org_id = $1
                  AND c.is_active = TRUE
                  AND c.is_attora_managed = TRUE
                ORDER BY c.name
                """,
                org["id"],
            )

            for camp in campaigns:
                rules = await conn.fetch(
                    """
                    SELECT step_order, after_minutes, message, is_final
                    FROM campaign_follow_ups
                    WHERE campaign_id = $1 AND is_active = TRUE
                    ORDER BY step_order
                    """,
                    camp["id"],
                )
                if not rules:
                    continue

                rule_list = [dict(r) for r in rules]
                print(
                    f"\n  Campaign {camp['name']!r} "
                    f"(keyword={camp['keyword']!r}, "
                    f"{len(rule_list)} touches)"
                )

                subs = await conn.fetch(
                    """
                    SELECT id, manychat_subscriber_id, first_name, last_name,
                           hyros_purchased, buyer_stage, last_user_message_at
                    FROM subscribers
                    WHERE org_id = $1 AND attora_campaign_id = $2
                    """,
                    org["id"],
                    camp["id"],
                )

                eligible_in_camp = 0

                for sub in subs:
                    grand_scanned += 1

                    if sub["hyros_purchased"] or sub["buyer_stage"] in _PURCHASE_STAGES:
                        skip_purchased += 1
                        continue

                    conv = await conn.fetchrow(
                        """
                        SELECT id, started_at, created_at, follow_up_attempts,
                               last_follow_up_at
                        FROM conversations
                        WHERE subscriber_id = $1 AND status = 'active'
                        ORDER BY last_activity_at DESC NULLS LAST
                        LIMIT 1
                        """,
                        sub["id"],
                    )
                    if conv is None:
                        skip_no_conv += 1
                        continue

                    attempts = conv["follow_up_attempts"]
                    if attempts >= len(rule_list):
                        skip_sequence_done += 1
                        continue

                    next_rule = rule_list[attempts]

                    if attempts == 0:
                        silence_anchor = (
                            sub["last_user_message_at"]
                            or conv["started_at"]
                            or conv["created_at"]
                        )
                        if silence_anchor is None:
                            skip_threshold += 1
                            continue
                        if silence_anchor.tzinfo is None:
                            silence_anchor = silence_anchor.replace(
                                tzinfo=timezone.utc
                            )
                        elapsed_min = (
                            now - silence_anchor
                        ).total_seconds() / 60.0
                        timing_note = "since last user msg / conv start"
                    else:
                        anchor = conv["last_follow_up_at"]
                        if anchor is None:
                            skip_threshold += 1
                            continue
                        if anchor.tzinfo is None:
                            anchor = anchor.replace(tzinfo=timezone.utc)
                        elapsed_min = (now - anchor).total_seconds() / 60.0
                        timing_note = "since prev follow-up"

                    if elapsed_min < next_rule["after_minutes"]:
                        skip_threshold += 1
                        continue

                    last_msg = await conn.fetchrow(
                        """
                        SELECT sender FROM messages
                        WHERE conversation_id = $1
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        conv["id"],
                    )
                    if last_msg is None or last_msg["sender"] == "user":
                        skip_engaged += 1
                        continue

                    eligible_in_camp += 1
                    grand_eligible += 1
                    name = " ".join(
                        x for x in (sub["first_name"], sub["last_name"]) if x
                    ) or "(no name)"
                    print(
                        f"    → {sub['manychat_subscriber_id']:>20}  {name:<25}  "
                        f"{elapsed_min:7.1f} min ({timing_note})  "
                        f"→ Touch {next_rule['step_order']}"
                        f"{' [FINAL]' if next_rule['is_final'] else ''}"
                    )

                print(f"    eligible in this campaign: {eligible_in_camp}")

        print("\n=== SUMMARY ===")
        print(f"subscribers scanned  : {grand_scanned}")
        print(f"would send a nudge   : {grand_eligible}")
        print(f"skip — already bought: {skip_purchased}")
        print(f"skip — no active conv: {skip_no_conv}")
        print(f"skip — sequence done : {skip_sequence_done}")
        print(f"skip — not silent yet: {skip_threshold}")
        print(f"skip — user replied  : {skip_engaged}")

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--org-slug",
        default=None,
        help="Limit preview to a single org (e.g. warrior-babe)",
    )
    args = parser.parse_args()
    asyncio.run(_preview(args.org_slug))


if __name__ == "__main__":
    main()
