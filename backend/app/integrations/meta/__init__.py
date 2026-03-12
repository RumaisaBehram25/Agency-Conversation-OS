"""
Attora — Meta Integrations

Meta Conversions API (CAPI) client for conversion event tracking.
"""

from app.integrations.meta.capi import fire_conversion_event

__all__ = ["fire_conversion_event"]
