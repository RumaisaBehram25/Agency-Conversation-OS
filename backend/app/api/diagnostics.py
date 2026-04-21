"""
Attora — Credential Diagnostics

GET /api/organizations/{org_id}/diagnose — probe the stored ManyChat + Meta
credentials against each provider's API and report what actually works.

Used to answer "did the client give us working keys with the right
permissions?" without needing to test each key by hand.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.organization import Organization
from app.models.user import OrgUser, User
from app.security.encryption import decrypt_value

logger = logging.getLogger(__name__)

router = APIRouter()

_GRAPH_API_VERSION = "v21.0"
_GRAPH_API_BASE = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"
_MANYCHAT_API_BASE = "https://api.manychat.com/fb"
_HTTP_TIMEOUT = 10.0

# Minimum Meta permissions we need for ad-spend sync + CAPI
_REQUIRED_META_SCOPES = {
    "ads_read",          # needed for Marketing API reads (campaign_metrics sync)
    "ads_management",    # needed for CAPI event posting in some setups
    "business_management",  # typical for system-user tokens
}


def _status(ok: bool, label: str, detail: Any = None) -> dict:
    return {"ok": ok, "label": label, "detail": detail}


async def _verify_org_membership(
    db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(OrgUser)
        .where(OrgUser.user_id == user_id)
        .where(OrgUser.org_id == org_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )


async def _probe_manychat(api_key: str) -> dict:
    """Hit ManyChat's page info endpoint to verify the token + page connection."""
    if not api_key:
        return _status(False, "manychat_api_key", "not set on organization")

    url = f"{_MANYCHAT_API_BASE}/page/getInfo"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        return _status(False, "manychat_api_key", f"network error: {e}")

    if r.status_code == 401:
        return _status(False, "manychat_api_key", "401 Unauthorized — token is invalid or revoked")
    if r.status_code >= 400:
        return _status(False, "manychat_api_key", f"{r.status_code}: {r.text[:200]}")

    body = r.json()
    if body.get("status") != "success":
        return _status(False, "manychat_api_key", f"non-success response: {body}")

    page = body.get("data") or {}
    return _status(
        True,
        "manychat_api_key",
        {
            "page_id": page.get("id"),
            "name": page.get("name"),
            "username": page.get("username"),
            "category": page.get("category"),
        },
    )


async def _probe_meta_token(token: str) -> dict:
    """Call debug_token to see scopes, app ownership, and expiry."""
    if not token:
        return _status(False, "meta_capi_token", "not set on organization")

    url = f"{_GRAPH_API_BASE}/debug_token"
    params = {"input_token": token, "access_token": token}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params)
    except httpx.HTTPError as e:
        return _status(False, "meta_capi_token", f"network error: {e}")

    if r.status_code >= 400:
        return _status(False, "meta_capi_token", f"{r.status_code}: {r.text[:300]}")

    data = (r.json() or {}).get("data") or {}
    if not data.get("is_valid"):
        return _status(False, "meta_capi_token", f"invalid token: {data}")

    scopes = set(data.get("scopes") or [])
    missing = _REQUIRED_META_SCOPES - scopes
    return _status(
        not missing,
        "meta_capi_token",
        {
            "app_id": data.get("app_id"),
            "application": data.get("application"),
            "type": data.get("type"),
            "expires_at": data.get("expires_at"),  # 0 = never expires
            "data_access_expires_at": data.get("data_access_expires_at"),
            "scopes": sorted(scopes),
            "missing_required_scopes": sorted(missing),
        },
    )


async def _probe_meta_ad_account(ad_account_id: str, token: str) -> dict:
    """Test that the token can actually read the ad account."""
    if not ad_account_id:
        return _status(False, "meta_ad_account_id", "not set on organization")
    if not token:
        return _status(False, "meta_ad_account_id", "cannot test without meta_capi_token")

    acct = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"
    url = f"{_GRAPH_API_BASE}/{acct}"
    params = {"fields": "name,account_status,currency,timezone_name", "access_token": token}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params)
    except httpx.HTTPError as e:
        return _status(False, "meta_ad_account_id", f"network error: {e}")

    if r.status_code >= 400:
        return _status(
            False,
            "meta_ad_account_id",
            f"{r.status_code}: {r.text[:300]} — token likely lacks ads_read on this account",
        )
    return _status(True, "meta_ad_account_id", r.json())


async def _probe_meta_pixel(pixel_id: str, token: str) -> dict:
    """Test that the token can read pixel metadata (needed for CAPI posts)."""
    if not pixel_id:
        return _status(False, "meta_pixel_id", "not set on organization")
    if not token:
        return _status(False, "meta_pixel_id", "cannot test without meta_capi_token")

    url = f"{_GRAPH_API_BASE}/{pixel_id}"
    params = {"fields": "name,last_fired_time,is_created_by_business", "access_token": token}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params)
    except httpx.HTTPError as e:
        return _status(False, "meta_pixel_id", f"network error: {e}")

    if r.status_code >= 400:
        return _status(
            False,
            "meta_pixel_id",
            f"{r.status_code}: {r.text[:300]} — token likely lacks access to this pixel",
        )
    return _status(True, "meta_pixel_id", r.json())


async def _probe_meta_page(page_id: str, token: str) -> dict:
    """Test that the token can read the FB page linked to the pixel."""
    if not page_id:
        return _status(False, "meta_page_id", "not set on organization (ok for IG-only setups)")
    if not token:
        return _status(False, "meta_page_id", "cannot test without meta_capi_token")

    url = f"{_GRAPH_API_BASE}/{page_id}"
    params = {"fields": "name,username,fan_count", "access_token": token}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params)
    except httpx.HTTPError as e:
        return _status(False, "meta_page_id", f"network error: {e}")

    if r.status_code >= 400:
        return _status(False, "meta_page_id", f"{r.status_code}: {r.text[:300]}")
    return _status(True, "meta_page_id", r.json())


@router.get("/{org_id}/diagnose")
async def diagnose_credentials(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Probe the org's stored ManyChat + Meta credentials and report what works.

    Runs live calls against ManyChat and the Meta Graph API using the
    decrypted keys, then returns a per-check pass/fail. Safe to call
    repeatedly — it doesn't mutate anything.
    """
    await _verify_org_membership(db, current_user.id, org_id)

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Decrypt secrets (non-fatal if decryption fails — report and continue)
    try:
        manychat_key = decrypt_value(org.manychat_api_key) if org.manychat_api_key else ""
    except Exception as e:
        manychat_key = ""
        logger.warning(f"Failed to decrypt manychat_api_key for org {org_id}: {e}")

    try:
        meta_token = decrypt_value(org.meta_capi_token) if org.meta_capi_token else ""
    except Exception as e:
        meta_token = ""
        logger.warning(f"Failed to decrypt meta_capi_token for org {org_id}: {e}")

    manychat_result = await _probe_manychat(manychat_key)
    meta_token_result = await _probe_meta_token(meta_token)
    meta_ad_account_result = await _probe_meta_ad_account(org.meta_ad_account_id or "", meta_token)
    meta_pixel_result = await _probe_meta_pixel(org.meta_pixel_id or "", meta_token)
    meta_page_result = await _probe_meta_page(org.meta_page_id or "", meta_token)

    checks = [
        manychat_result,
        meta_token_result,
        meta_ad_account_result,
        meta_pixel_result,
        meta_page_result,
    ]
    return {
        "org_id": str(org_id),
        "org_name": org.name,
        "all_ok": all(c["ok"] for c in checks),
        "checks": checks,
    }
