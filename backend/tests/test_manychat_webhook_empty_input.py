"""Regression test for blank ManyChat webhook input handling."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.api.manychat_webhook import manychat_webhook
from app.schemas.manychat import ManyChatCustomFields, ManyChatSubscriber, ManyChatWebhookRequest


@pytest.mark.asyncio
async def test_manychat_webhook_returns_safe_response_for_empty_input(monkeypatch):
    from app.api import manychat_webhook as webhook_module

    request = ManyChatWebhookRequest(
        subscriber=ManyChatSubscriber(
            id="mc-123",
            first_name="Sam",
            last_name="Taylor",
            custom_fields=ManyChatCustomFields(attora_buyer_stage="awareness"),
        ),
        last_input_text="   ",
        channel="instagram",
    )

    org_id = uuid.uuid4()
    db = AsyncMock()

    ai_pipeline_called = False

    async def _fail_if_called(*args, **kwargs):
        nonlocal ai_pipeline_called
        ai_pipeline_called = True
        raise AssertionError("generate_ai_response should not be called for blank input")

    monkeypatch.setattr(webhook_module, "generate_ai_response", _fail_if_called)

    response = await manychat_webhook(request=request, org_id=org_id, db=db)

    assert response.version == "v2"
    assert response.content.messages[0].text == "Please send a message so I can help you 🙂"
    assert ai_pipeline_called is False
