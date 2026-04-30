"""
Diagnostic script — list AdCampaign rows for troubleshooting ManyChat mapping.

Run with:
    docker compose exec api python scripts/list_ad_campaigns.py
"""

import asyncio
import sys
import os
sys.path.insert(0, "/app")

from sqlalchemy import select
from app.database import async_session_factory
from app.models.campaign import AdCampaign


async def main():
    async with async_session_factory() as db:
        result = await db.execute(
            select(
                AdCampaign.id,
                AdCampaign.name,
                AdCampaign.keyword,
                AdCampaign.source_type,
                AdCampaign.channel,
                AdCampaign.created_at,
            ).order_by(AdCampaign.created_at.desc())
        )
        rows = result.all()
        print(f"Found {len(rows)} campaigns:\n")
        for r in rows:
            print({
                "id": str(r.id),
                "name": r.name,
                "keyword": r.keyword,
                "source_type": r.source_type,
                "channel": r.channel,
                "created_at": str(r.created_at),
            })

if __name__ == '__main__':
    asyncio.run(main())
