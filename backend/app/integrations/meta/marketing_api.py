"""
Attora — Meta Marketing API Client

Fetches campaign-level ad spend data from the Meta Graph API.
Used by the ad_spend_sync job to populate daily_analytics.ad_spend.

Uses the same access token as CAPI (system user tokens typically
have both CAPI and Marketing API read permissions).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GRAPH_API_VERSION = "v21.0"
_GRAPH_API_BASE = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"
_DEFAULT_TIMEOUT = 30.0


async def fetch_daily_ad_spend(
    ad_account_id: str,
    access_token: str,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    """
    Fetch daily ad spend from Meta Marketing API.

    Args:
        ad_account_id: Meta ad account ID (with or without 'act_' prefix).
        access_token: System user token with ads_read permission.
        date_from: Start date (inclusive).
        date_to: End date (inclusive).

    Returns:
        List of {"date": "YYYY-MM-DD", "spend": float} dicts.
    """
    # Ensure act_ prefix
    if not ad_account_id.startswith("act_"):
        ad_account_id = f"act_{ad_account_id}"

    url = f"{_GRAPH_API_BASE}/{ad_account_id}/insights"
    params = {
        "access_token": access_token,
        "fields": "spend",
        "time_range": f'{{"since":"{date_from.isoformat()}","until":"{date_to.isoformat()}"}}',
        "time_increment": "1",  # daily breakdown
        "level": "account",  # aggregate across all campaigns
        "limit": "500",
    }

    results: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            while url:
                response = await client.get(url, params=params)
                response.raise_for_status()
                body = response.json()

                for row in body.get("data", []):
                    spend = float(row.get("spend", "0"))
                    row_date = row.get("date_start", "")
                    if row_date and spend >= 0:
                        results.append({
                            "date": row_date,
                            "spend": spend,
                        })

                # Handle pagination
                paging = body.get("paging", {})
                next_url = paging.get("next")
                if next_url:
                    url = next_url
                    params = {}  # next URL includes all params
                else:
                    url = None

        logger.info(
            f"Marketing API: fetched {len(results)} days of spend data "
            f"for {ad_account_id} ({date_from} to {date_to})"
        )
        return results

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        error_body = e.response.text[:500]

        if status_code in (401, 403):
            logger.error(
                f"Marketing API auth error for {ad_account_id}: "
                f"{status_code} — token may be invalid or missing ads_read permission. "
                f"Response: {error_body}"
            )
        elif status_code == 429:
            logger.warning(
                f"Marketing API rate limited for {ad_account_id}. "
                f"Response: {error_body}"
            )
        else:
            logger.error(
                f"Marketing API HTTP error for {ad_account_id}: "
                f"{status_code}: {error_body}"
            )
        return []

    except httpx.TimeoutException:
        logger.error(f"Marketing API timeout for {ad_account_id}")
        return []

    except Exception as e:
        logger.error(f"Marketing API request failed for {ad_account_id}: {e}")
        return []
