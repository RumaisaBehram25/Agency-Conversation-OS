"""
Attora — AI Config API Routes

GET  /api/ai-config  — Get the org's AI config (or return defaults)
PUT  /api/ai-config  — Upsert AI config
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ai_config import AIConfig
from app.models.user import User
from app.schemas.ai_config import AIConfigResponse, AIConfigUpdate
from app.api.deps import get_current_user, get_org_id

router = APIRouter()


@router.get("", response_model=AIConfigResponse)
async def get_ai_config(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> AIConfigResponse:
    """
    Get the org's AI configuration.

    Returns the existing config, or defaults if none has been created yet.
    """
    result = await db.execute(
        select(AIConfig).where(AIConfig.org_id == org_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        # Return defaults — no config row exists yet
        return AIConfigResponse(
            brand_voice=None,
            persona_name=None,
            product_knowledge=None,
            compliance_rules=None,
            conversion_playbook=None,
            objection_handlers=None,
            greeting_message=None,
            fallback_message=None,
            max_messages_before_handoff=50,
        )

    return AIConfigResponse.model_validate(config)


@router.put("", response_model=AIConfigResponse)
async def upsert_ai_config(
    request: AIConfigUpdate,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> AIConfigResponse:
    """
    Create or update the org's AI configuration.

    If no config exists, a new one is created. Otherwise, existing config is updated.
    """
    result = await db.execute(
        select(AIConfig).where(AIConfig.org_id == org_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        # Create new config
        config = AIConfig(
            org_id=org_id,
            brand_voice=request.brand_voice,
            persona_name=request.persona_name,
            product_knowledge=request.product_knowledge,
            compliance_rules=request.compliance_rules,
            conversion_playbook=request.conversion_playbook,
            objection_handlers=request.objection_handlers,
            greeting_message=request.greeting_message,
            fallback_message=request.fallback_message,
            max_messages_before_handoff=request.max_messages_before_handoff,
        )
        db.add(config)
    else:
        # Update existing config
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)

    await db.flush()
    await db.refresh(config)

    return AIConfigResponse.model_validate(config)
