"""
Seed script — inserts 30 days of realistic test analytics data.

Run with:
    docker compose exec api python scripts/seed_analytics.py
"""

import asyncio
import random
import uuid
from datetime import date, timedelta

import sys
import os
sys.path.insert(0, "/app")

from app.database import async_session_factory
from app.models.analytics import DailyAnalytics
from app.models.organization import Organization
from sqlalchemy import select, delete


ORG_SLUG = "my-org"  # change if your org slug is different


async def seed():
    async with async_session_factory() as db:
        # Find the org
        result = await db.execute(
            select(Organization).where(Organization.slug == ORG_SLUG)
        )
        org = result.scalar_one_or_none()
        if not org:
            print(f"ERROR: No org with slug '{ORG_SLUG}' found.")
            return

        print(f"Seeding analytics for org: {org.name} ({org.id})")

        # Clear existing test data for this org
        await db.execute(
            delete(DailyAnalytics).where(DailyAnalytics.org_id == org.id)
        )

        today = date.today()
        rows = []

        for i in range(30):
            day = today - timedelta(days=29 - i)

            # Gradually increasing trend over 30 days
            growth = 1 + (i / 30) * 0.8
            noise = random.uniform(0.85, 1.15)

            new_convos = int(random.randint(8, 15) * growth * noise)
            active_convos = int(new_convos * random.uniform(0.6, 0.9))
            total_msgs = new_convos * random.randint(4, 9)
            conversions = max(0, int(new_convos * random.uniform(0.08, 0.18)))
            conversion_value = round(conversions * random.uniform(45, 120), 2)
            ad_spend = round(random.uniform(40, 90) * growth * noise, 2)
            avg_response_ms = random.randint(800, 2800)
            tokens = total_msgs * random.randint(300, 600)
            ai_cost = round(tokens * 0.000003, 4)
            fallbacks = max(0, int(total_msgs * random.uniform(0, 0.05)))
            cpa = round(ad_spend / conversions, 2) if conversions > 0 else None
            roas = round(conversion_value / ad_spend, 2) if ad_spend > 0 else None
            avg_msgs = round(total_msgs / new_convos, 1) if new_convos > 0 else 0
            ccr = round(conversions / new_convos, 4) if new_convos > 0 else 0

            rows.append(DailyAnalytics(
                id=uuid.uuid4(),
                org_id=org.id,
                date=day,
                channel=None,  # account-level total
                new_conversations=new_convos,
                active_conversations=active_convos,
                total_messages=total_msgs,
                avg_messages_per_conversation=avg_msgs,
                avg_ai_response_time_ms=avg_response_ms,
                conversions=conversions,
                conversion_value=conversion_value,
                conversion_rate=ccr,
                ad_spend=ad_spend,
                cpa=cpa,
                roas=roas,
                ai_tokens_used=tokens,
                ai_cost=ai_cost,
                fallback_count=fallbacks,
            ))

        db.add_all(rows)
        await db.commit()

        total_convos = sum(r.new_conversations for r in rows)
        total_conversions = sum(r.conversions for r in rows)
        total_revenue = sum(r.conversion_value for r in rows)
        total_spend = sum(r.ad_spend for r in rows)

        print(f"\n✓ Seeded 30 days of analytics data")
        print(f"  Conversations : {total_convos}")
        print(f"  Conversions   : {total_conversions}")
        print(f"  Revenue       : ${total_revenue:,.2f}")
        print(f"  Ad Spend      : ${total_spend:,.2f}")
        print(f"  ROAS          : {round(total_revenue / total_spend, 2)}x")
        print(f"\nOpen the Analytics page in the UI to see the charts.")


if __name__ == "__main__":
    asyncio.run(seed())
