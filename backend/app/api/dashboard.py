"""
Attora — Dashboard Overview API Route

GET  /api/dashboard  — Single endpoint for the dashboard overview page
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardOverviewResponse
from app.services.analytics_service import get_dashboard_overview
from app.api.deps import get_current_user, get_org_id

router = APIRouter()


@router.get("", response_model=DashboardOverviewResponse)
async def dashboard_overview(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> DashboardOverviewResponse:
    """
    Get the dashboard overview data.

    Returns:
    - CPQC with 7-day trend
    - CCR with 7-day trend
    - Average messages per conversation (steps), all-time
    - Active conversations count
    - Today's conversions and revenue
    - Campaign health array (green/yellow/red per channel)
    """
    data = await get_dashboard_overview(db, org_id)
    return DashboardOverviewResponse(**data)
