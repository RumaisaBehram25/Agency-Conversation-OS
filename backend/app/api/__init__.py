from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.manychat_webhook import router as manychat_router
from app.api.organizations import router as organizations_router
from app.api.products import router as products_router
from app.api.ai_config import router as ai_config_router
from app.api.conversations import router as conversations_router
from app.api.subscribers import router as subscribers_router
from app.api.analytics import router as analytics_router
from app.api.dashboard import router as dashboard_router
from app.api.settings import router as settings_router
from app.api.campaigns import router as campaigns_router
from app.api.cron import router as cron_router
from app.api.olap import router as olap_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(organizations_router, prefix="/organizations", tags=["organizations"])
api_router.include_router(manychat_router, prefix="/manychat", tags=["manychat"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(ai_config_router, prefix="/ai-config", tags=["ai-config"])
api_router.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
api_router.include_router(subscribers_router, prefix="/subscribers", tags=["subscribers"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(campaigns_router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(cron_router, prefix="/cron", tags=["cron"])
api_router.include_router(olap_router, prefix="/olap", tags=["olap"])
