"""
Attora — Config Loader

Loads organization configuration (AIConfig, Products, Organization settings)
from Redis cache (5-minute TTL) with Postgres fallback. Provides a single
cached OrgConfig object for the AI engine pipeline.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig
from app.models.organization import Organization
from app.models.product import Product
from app.schemas.ai_engine import AIConfigData, OrgConfig, ProductInfo

logger = logging.getLogger(__name__)

# Redis cache key prefix and TTL
_CACHE_PREFIX = "orgconfig:"
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _cache_key(org_id: str | uuid.UUID) -> str:
    """Build Redis cache key for an organization config."""
    return f"{_CACHE_PREFIX}{str(org_id)}"


async def load_org_config(
    org_id: uuid.UUID,
    db: AsyncSession,
    redis_client=None,
    *,
    force_refresh: bool = False,
) -> OrgConfig:
    """
    Load organization config with Redis caching.

    Steps:
    1. Check Redis cache (unless force_refresh)
    2. On cache miss, load from Postgres
    3. Store in Redis with 5-min TTL
    4. Return OrgConfig

    Args:
        org_id: Organization UUID.
        db: Async database session.
        redis_client: Optional Redis client (skips cache if None).
        force_refresh: If True, bypass cache and reload from DB.

    Returns:
        OrgConfig with all data needed for AI pipeline.
    """
    cache_key = _cache_key(org_id)

    # ── Step 1: Try Redis cache ───────────────────────────────
    if redis_client and not force_refresh:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug(f"Config cache hit for org {org_id}")
                return OrgConfig.model_validate_json(cached)
        except Exception as e:
            logger.warning(f"Redis cache read failed for org {org_id}: {e}")

    # ── Step 2: Load from Postgres ────────────────────────────
    logger.debug(f"Loading config from DB for org {org_id}")

    # Load organization
    org_result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise ValueError(f"Organization {org_id} not found")

    # Load AI config
    ai_config_result = await db.execute(
        select(AIConfig).where(AIConfig.org_id == org_id)
    )
    ai_config = ai_config_result.scalar_one_or_none()

    ai_config_data = AIConfigData()
    if ai_config:
        ai_config_data = AIConfigData(
            brand_voice=ai_config.brand_voice,
            persona_name=ai_config.persona_name,
            system_prompt_override=ai_config.system_prompt_override,
            product_knowledge=ai_config.product_knowledge,
            compliance_rules=ai_config.compliance_rules,
            conversion_playbook=ai_config.conversion_playbook,
            objection_handlers=ai_config.objection_handlers,
            greeting_message=ai_config.greeting_message,
            fallback_message=ai_config.fallback_message,
            max_messages_before_handoff=ai_config.max_messages_before_handoff,
        )

    # Load active products
    products_result = await db.execute(
        select(Product)
        .where(Product.org_id == org_id, Product.is_active.is_(True))
        .order_by(Product.sort_order)
    )
    products = products_result.scalars().all()

    product_list = [
        ProductInfo(
            id=str(p.id),
            name=p.name,
            description=p.description,
            price=float(p.price) if p.price is not None else None,
            currency=p.currency,
            checkout_url=p.checkout_url,
            conversion_value=float(p.conversion_value) if p.conversion_value is not None else None,
            eligibility_criteria=p.eligibility_criteria,
            objection_responses=p.objection_responses,
            is_active=p.is_active,
        )
        for p in products
    ]

    # Decrypt Meta CAPI token if present
    meta_capi_token = None
    if org.meta_capi_token:
        try:
            from app.security.encryption import decrypt_value
            meta_capi_token = decrypt_value(org.meta_capi_token)
        except Exception as e:
            logger.warning(f"Failed to decrypt meta_capi_token for org {org_id}: {e}")

    org_config = OrgConfig(
        org_id=str(org_id),
        org_name=org.name,
        org_slug=org.slug,
        meta_pixel_id=org.meta_pixel_id,
        meta_capi_token=meta_capi_token,
        meta_page_id=org.meta_page_id,
        ai_config=ai_config_data,
        products=product_list,
    )

    # ── Step 3: Cache in Redis ────────────────────────────────
    if redis_client:
        try:
            await redis_client.setex(
                cache_key,
                _CACHE_TTL_SECONDS,
                org_config.model_dump_json(),
            )
            logger.debug(f"Cached config for org {org_id} (TTL={_CACHE_TTL_SECONDS}s)")
        except Exception as e:
            logger.warning(f"Redis cache write failed for org {org_id}: {e}")

    return org_config


async def invalidate_org_config(
    org_id: uuid.UUID,
    redis_client=None,
) -> None:
    """
    Invalidate cached organization config.

    Call this when org settings, AI config, or products are updated.
    """
    if redis_client:
        try:
            cache_key = _cache_key(org_id)
            await redis_client.delete(cache_key)
            logger.info(f"Invalidated config cache for org {org_id}")
        except Exception as e:
            logger.warning(f"Redis cache invalidation failed for org {org_id}: {e}")
