"""
Attora — Meta Marketing API Client

Fetches ad performance data from the Meta Graph API at multiple levels
(account, campaign, ad set, ad) with optional demographic and platform
breakdowns.

Used by the ad_spend_sync job and analytics pipeline.

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


# ---------------------------------------------------------------------------
# Helpers — parse Meta's nested actions / cost arrays into flat dicts
# ---------------------------------------------------------------------------

_ACTION_TYPE_MAP = {
    "lead": "leads",
    "link_click": "link_clicks",
    "landing_page_view": "landing_page_views",
    "video_view": "video_views",
    "post_engagement": "post_engagement",
    "onsite_conversion.messaging_conversation_started_7d": "messaging_conversations_started",
    "onsite_conversion.messaging_first_reply": "messaging_first_reply",
}


def _parse_actions(actions_list: list[dict[str, Any]] | None) -> dict[str, int]:
    """
    Flatten Meta's actions array into a dict with human-friendly keys.

    Returns a dict with every key from _ACTION_TYPE_MAP, defaulting to 0.
    """
    result: dict[str, int] = {v: 0 for v in _ACTION_TYPE_MAP.values()}
    if not actions_list:
        return result
    for action in actions_list:
        action_type = action.get("action_type", "")
        mapped = _ACTION_TYPE_MAP.get(action_type)
        if mapped:
            result[mapped] = int(action.get("value", 0))
    return result


def _parse_cost_per_action(
    cost_list: list[dict[str, Any]] | None,
) -> dict[str, float | None]:
    """
    Extract cost_per_lead from Meta's cost_per_action_type array.

    Returns {"cost_per_lead": <float or None>}.
    """
    result: dict[str, float | None] = {"cost_per_lead": None}
    if not cost_list:
        return result
    for item in cost_list:
        if item.get("action_type") == "lead":
            try:
                result["cost_per_lead"] = float(item["value"])
            except (KeyError, ValueError, TypeError):
                pass
            break
    return result


# ---------------------------------------------------------------------------
# Shared fields / constants
# ---------------------------------------------------------------------------

_INSIGHTS_FIELDS_CORE = (
    "spend,impressions,clicks,reach,frequency,cpc,cpm,ctr,"
    "actions,cost_per_action_type"
)


def _ensure_act_prefix(ad_account_id: str) -> str:
    if not ad_account_id.startswith("act_"):
        return f"act_{ad_account_id}"
    return ad_account_id


def _build_time_range(date_from: date, date_to: date) -> str:
    return f'{{"since":"{date_from.isoformat()}","until":"{date_to.isoformat()}"}}'


def _flatten_insight_row(
    row: dict[str, Any],
    extra_id_fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    Convert a raw API insight row into a flat dict with parsed actions.
    """
    flat: dict[str, Any] = {
        "date": row.get("date_start", ""),
        "spend": float(row.get("spend", "0")),
        "impressions": int(row.get("impressions", "0")),
        "clicks": int(row.get("clicks", "0")),
        "reach": int(row.get("reach", "0")),
        "frequency": float(row.get("frequency", "0")),
        "cpc": float(row.get("cpc", "0")),
        "cpm": float(row.get("cpm", "0")),
        "ctr": float(row.get("ctr", "0")),
    }

    # Copy over level-specific ID/name fields (campaign_id, adset_name, etc.)
    for field in extra_id_fields or []:
        flat[field] = row.get(field, "")

    # Flatten actions and cost_per_action
    flat.update(_parse_actions(row.get("actions")))
    flat.update(_parse_cost_per_action(row.get("cost_per_action_type")))

    return flat


# ---------------------------------------------------------------------------
# Campaign-level insights
# ---------------------------------------------------------------------------

async def fetch_campaign_insights(
    ad_account_id: str,
    access_token: str,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    """
    Fetch daily campaign-level insights from Meta Marketing API.

    Returns one flat dict per campaign per day with core metrics,
    parsed action counts, and cost_per_lead.
    """
    ad_account_id = _ensure_act_prefix(ad_account_id)

    url: str | None = f"{_GRAPH_API_BASE}/{ad_account_id}/insights"
    params: dict[str, str] = {
        "access_token": access_token,
        "fields": f"campaign_id,campaign_name,{_INSIGHTS_FIELDS_CORE}",
        "time_range": _build_time_range(date_from, date_to),
        "time_increment": "1",
        "level": "campaign",
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
                    results.append(
                        _flatten_insight_row(
                            row,
                            extra_id_fields=["campaign_id", "campaign_name"],
                        )
                    )

                paging = body.get("paging", {})
                next_url = paging.get("next")
                if next_url:
                    url = next_url
                    params = {}
                else:
                    url = None

        logger.info(
            f"Marketing API: fetched {len(results)} campaign insight rows "
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


# ---------------------------------------------------------------------------
# Ad-set-level insights
# ---------------------------------------------------------------------------

async def fetch_adset_insights(
    ad_account_id: str,
    access_token: str,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    """
    Fetch daily ad-set-level insights from Meta Marketing API.

    Returns one flat dict per ad set per day with core metrics,
    parsed action counts, and cost_per_lead.
    """
    ad_account_id = _ensure_act_prefix(ad_account_id)

    url: str | None = f"{_GRAPH_API_BASE}/{ad_account_id}/insights"
    params: dict[str, str] = {
        "access_token": access_token,
        "fields": f"adset_id,adset_name,campaign_id,campaign_name,{_INSIGHTS_FIELDS_CORE}",
        "time_range": _build_time_range(date_from, date_to),
        "time_increment": "1",
        "level": "adset",
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
                    results.append(
                        _flatten_insight_row(
                            row,
                            extra_id_fields=[
                                "adset_id", "adset_name",
                                "campaign_id", "campaign_name",
                            ],
                        )
                    )

                paging = body.get("paging", {})
                next_url = paging.get("next")
                if next_url:
                    url = next_url
                    params = {}
                else:
                    url = None

        logger.info(
            f"Marketing API: fetched {len(results)} adset insight rows "
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


# ---------------------------------------------------------------------------
# Ad-level insights
# ---------------------------------------------------------------------------

async def fetch_ad_insights(
    ad_account_id: str,
    access_token: str,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    """
    Fetch daily ad-level insights from Meta Marketing API.

    Returns one flat dict per ad per day with core metrics,
    parsed action counts, and cost_per_lead.
    """
    ad_account_id = _ensure_act_prefix(ad_account_id)

    url: str | None = f"{_GRAPH_API_BASE}/{ad_account_id}/insights"
    params: dict[str, str] = {
        "access_token": access_token,
        "fields": f"ad_id,ad_name,adset_id,campaign_id,{_INSIGHTS_FIELDS_CORE}",
        "time_range": _build_time_range(date_from, date_to),
        "time_increment": "1",
        "level": "ad",
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
                    results.append(
                        _flatten_insight_row(
                            row,
                            extra_id_fields=[
                                "ad_id", "ad_name",
                                "adset_id", "campaign_id",
                            ],
                        )
                    )

                paging = body.get("paging", {})
                next_url = paging.get("next")
                if next_url:
                    url = next_url
                    params = {}
                else:
                    url = None

        logger.info(
            f"Marketing API: fetched {len(results)} ad insight rows "
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


# ---------------------------------------------------------------------------
# Breakdown insights (age/gender or platform/placement)
# ---------------------------------------------------------------------------

async def fetch_breakdown_insights(
    ad_account_id: str,
    access_token: str,
    date_from: date,
    date_to: date,
    breakdown_type: str,
) -> list[dict[str, Any]]:
    """
    Fetch campaign insights with demographic or platform breakdowns.

    Args:
        breakdown_type: "age_gender" or "platform".

    Returns list of dicts with a 'breakdown_key' constructed from the
    breakdown dimension values (e.g. "25-34_male" or "instagram_feed").
    """
    ad_account_id = _ensure_act_prefix(ad_account_id)

    if breakdown_type == "age_gender":
        breakdowns = "age,gender"
        breakdown_fields: list[str] = ["age", "gender"]
    elif breakdown_type == "platform":
        breakdowns = "publisher_platform,platform_position"
        breakdown_fields = ["publisher_platform", "platform_position"]
    else:
        logger.error(
            f"Marketing API: invalid breakdown_type '{breakdown_type}'. "
            f"Must be 'age_gender' or 'platform'."
        )
        return []

    url: str | None = f"{_GRAPH_API_BASE}/{ad_account_id}/insights"
    params: dict[str, str] = {
        "access_token": access_token,
        "fields": "campaign_id,spend,impressions,clicks,actions",
        "time_range": _build_time_range(date_from, date_to),
        "time_increment": "1",
        "level": "campaign",
        "breakdowns": breakdowns,
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
                    # Build the composite breakdown key
                    breakdown_key = "_".join(
                        row.get(field, "unknown") for field in breakdown_fields
                    )

                    parsed_actions = _parse_actions(row.get("actions"))

                    results.append({
                        "date": row.get("date_start", ""),
                        "campaign_id": row.get("campaign_id", ""),
                        "breakdown_type": breakdown_type,
                        "breakdown_key": breakdown_key,
                        "spend": float(row.get("spend", "0")),
                        "impressions": int(row.get("impressions", "0")),
                        "clicks": int(row.get("clicks", "0")),
                        "leads": parsed_actions.get("leads", 0),
                    })

                paging = body.get("paging", {})
                next_url = paging.get("next")
                if next_url:
                    url = next_url
                    params = {}
                else:
                    url = None

        logger.info(
            f"Marketing API: fetched {len(results)} breakdown ({breakdown_type}) rows "
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


# ---------------------------------------------------------------------------
# Campaign metadata (not insights — structural info)
# ---------------------------------------------------------------------------

async def fetch_campaign_metadata(
    ad_account_id: str,
    access_token: str,
) -> list[dict[str, Any]]:
    """
    Fetch campaign metadata (name, status, objective, budgets, dates).

    This hits the /campaigns edge, not /insights, so it returns structural
    info rather than performance metrics.
    """
    ad_account_id = _ensure_act_prefix(ad_account_id)

    url: str | None = f"{_GRAPH_API_BASE}/{ad_account_id}/campaigns"
    params: dict[str, str] = {
        "access_token": access_token,
        "fields": (
            "id,name,status,objective,"
            "daily_budget,lifetime_budget,start_time,created_time"
        ),
        "limit": "500",
    }

    results: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            while url:
                response = await client.get(url, params=params)
                response.raise_for_status()
                body = response.json()

                for campaign in body.get("data", []):
                    results.append({
                        "campaign_id": campaign.get("id", ""),
                        "name": campaign.get("name", ""),
                        "status": campaign.get("status", ""),
                        "objective": campaign.get("objective", ""),
                        "daily_budget": campaign.get("daily_budget"),
                        "lifetime_budget": campaign.get("lifetime_budget"),
                        "start_time": campaign.get("start_time"),
                        "created_time": campaign.get("created_time"),
                    })

                paging = body.get("paging", {})
                next_url = paging.get("next")
                if next_url:
                    url = next_url
                    params = {}
                else:
                    url = None

        logger.info(
            f"Marketing API: fetched {len(results)} campaigns "
            f"for {ad_account_id}"
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
