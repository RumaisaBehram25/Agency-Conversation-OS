"""
Attora — ManyChat Webhook Schemas

Pydantic models for ManyChat External Request webhook payloads
and the ManyChat v2 response format.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── ManyChat Webhook Request ──────────────────────────────────


class ManyChatCustomFields(BaseModel):
    """Custom fields sent by ManyChat in the webhook payload."""

    attora_buyer_stage: str | None = None
    ctwa_clid: str | None = None
    ad_id: str | None = None
    ad_set_id: str | None = None
    campaign_id: str | None = None
    # Organic Instagram/Facebook attribution. ManyChat must set this from
    # the comment/post trigger ({{trigger_post_id}} on IG, post id on FB)
    # for organic conversations to register in the Organic Posts analytics.
    post_id: str | None = None
    # Optional first-touch UTMs (map from ManyChat / landing flow)
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None

    class Config:
        extra = "allow"  # ManyChat may send additional custom fields


class ManyChatSubscriber(BaseModel):
    """Subscriber data from ManyChat webhook payload."""

    id: str = Field(..., description="ManyChat subscriber ID")
    key: str | None = Field(None, description="ManyChat subscriber key")
    page_id: str | None = Field(None, description="ManyChat page ID")
    first_name: str | None = None
    last_name: str | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    gender: str | None = None
    language: str | None = None
    custom_fields: ManyChatCustomFields = Field(
        default_factory=ManyChatCustomFields
    )


class ManyChatWebhookRequest(BaseModel):
    """
    Incoming webhook request from ManyChat External Request action.

    ManyChat sends subscriber data and the last user input text.
    The channel is determined by the page_id or can be passed explicitly.
    """

    subscriber: ManyChatSubscriber = Field(
        ..., description="Subscriber data from ManyChat"
    )
    last_input_text: str = Field(
        ..., description="The subscriber's last message text"
    )
    channel: str = Field(
        default="messenger",
        description="Messaging channel: whatsapp, messenger, instagram",
    )
    flow_id: str | None = Field(
        default=None,
        description="ManyChat flow namespace/id that triggered the webhook",
    )
    event_type: str | None = Field(
        default=None,
        description="Optional webhook event type (e.g. sent, clicked) when provided by flow setup",
    )
    clicked: bool | None = Field(
        default=None,
        description="Optional flag indicating this webhook was triggered by a button click",
    )
    button_clicked: bool | None = Field(
        default=None,
        description="Optional alias for clicked flag from flow payload",
    )


# ── ManyChat Webhook Response (v2 format) ─────────────────────


class ManyChatTextMessage(BaseModel):
    """A text message in ManyChat v2 response."""

    type: str = "text"
    text: str


class ManyChatAction(BaseModel):
    """An action in ManyChat v2 response (e.g., set custom field)."""

    action: str = "set_field_value"
    field_name: str
    value: str


class ManyChatQuickReply(BaseModel):
    """A quick reply button in ManyChat v2 response."""

    type: str = "node"
    caption: str


class ManyChatResponseContent(BaseModel):
    """Content block of ManyChat v2 response."""

    messages: list[ManyChatTextMessage] = Field(default_factory=list)
    actions: list[ManyChatAction] = Field(default_factory=list)
    quick_replies: list[ManyChatQuickReply] = Field(default_factory=list)


class ManyChatWebhookResponse(BaseModel):
    """
    ManyChat v2 response format.

    This is the structure ManyChat expects back from an External Request action.
    """

    version: str = "v2"
    content: ManyChatResponseContent = Field(
        default_factory=ManyChatResponseContent
    )

    @classmethod
    def from_ai_response(
        cls,
        response_text: str,
        buyer_stage: str | None = None,
        quick_replies: list[str] | None = None,
        custom_field_updates: dict[str, str | bool | int | float | None] | None = None,
    ) -> ManyChatWebhookResponse:
        """
        Build a ManyChat v2 response from AI engine output.

        Args:
            response_text: The AI-generated response text.
            buyer_stage: Updated buyer stage to set as custom field.
            quick_replies: Suggested quick reply button captions.
            custom_field_updates: Additional custom field key-value pairs.
                Non-string values (bool/int/float/None) are stringified — ManyChat
                custom fields are stored as strings on their side.
        """
        messages = [ManyChatTextMessage(text=response_text)]

        actions: list[ManyChatAction] = []
        if buyer_stage:
            actions.append(
                ManyChatAction(
                    action="set_field_value",
                    field_name="attora_buyer_stage",
                    value=buyer_stage,
                )
            )
        if custom_field_updates:
            for field_name, value in custom_field_updates.items():
                # ManyChat fields are strings. Stringify booleans as lowercase
                # ("true"/"false") to match JSON convention; skip nulls entirely.
                if value is None:
                    continue
                if isinstance(value, bool):
                    str_value = "true" if value else "false"
                else:
                    str_value = str(value)
                actions.append(
                    ManyChatAction(
                        action="set_field_value",
                        field_name=field_name,
                        value=str_value,
                    )
                )

        qr_buttons: list[ManyChatQuickReply] = []
        if quick_replies:
            for caption in quick_replies[:3]:  # ManyChat max 3 quick replies
                qr_buttons.append(ManyChatQuickReply(caption=caption))

        return cls(
            content=ManyChatResponseContent(
                messages=messages,
                actions=actions,
                quick_replies=qr_buttons,
            )
        )
