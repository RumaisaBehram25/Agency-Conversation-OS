"""
Attora — SQLAlchemy Models

All models are imported here so Alembic can detect them for autogeneration.
"""

from app.models.base import Base, OrgScopedMixin, TimestampMixin
from app.models.organization import Organization
from app.models.user import User, OrgUser
from app.models.product import Product
from app.models.ai_config import AIConfig
from app.models.subscriber import Subscriber
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.conversion import ConversionEvent
from app.models.analytics import DailyAnalytics
from app.models.campaign_metrics import CampaignMetric, CampaignBreakdown
from app.models.knowledge_document import KnowledgeDocument
from app.models.ai_usage_event import AIUsageEvent

__all__ = [
    "Base",
    "TimestampMixin",
    "OrgScopedMixin",
    "Organization",
    "User",
    "OrgUser",
    "Product",
    "AIConfig",
    "Subscriber",
    "Conversation",
    "Message",
    "ConversionEvent",
    "DailyAnalytics",
    "CampaignMetric",
    "CampaignBreakdown",
    "KnowledgeDocument",
    "AIUsageEvent",
]
