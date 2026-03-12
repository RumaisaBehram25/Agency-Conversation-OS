"""
Attora — Health Check Endpoints

GET /api/health — Returns service status including database and Redis connectivity.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.config import settings
from app.database import get_db
from app.redis import get_redis

router = APIRouter()


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> dict:
    """
    Comprehensive health check endpoint.

    Returns status of the API server, database, and Redis connections.
    """
    result = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "services": {},
    }

    # Check database connectivity
    try:
        await db.execute(text("SELECT 1"))
        result["services"]["database"] = {"status": "healthy"}
    except Exception as e:
        result["services"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        result["status"] = "degraded"

    # Check Redis connectivity
    try:
        await redis_client.ping()
        result["services"]["redis"] = {"status": "healthy"}
    except Exception as e:
        result["services"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        result["status"] = "degraded"

    return result


@router.get("/health/ping")
async def ping() -> dict:
    """Lightweight liveness probe — no dependency checks."""
    return {"status": "ok"}
