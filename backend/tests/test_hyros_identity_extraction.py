"""Hyros lead/sale identity extraction (attora_id / attora_sub)."""

from app.services.hyros_service import _extract_attora_identity

_ATTORA_ID = "550e8400-e29b-41d4-a716-446655440000"
_ATTORA_SUB = "mc_subscriber_dynamic_42"


def test_extracts_attora_id_and_attora_sub_from_sources_and_dynamic_sources() -> None:
    """Dynamic URL params mirrored into sources / dynamicSources rows."""
    raw = {
        "id": "lead-1",
        "email": "lead@example.com",
        "tags": [],
        "dynamicSources": [
            {"name": "attora_sub", "value": _ATTORA_SUB},
        ],
        "sources": [
            {
                "sourceType": "URL_PARAMETER",
                "name": "attora_id",
                "value": _ATTORA_ID,
            },
        ],
    }
    attora_id, attora_sub = _extract_attora_identity(raw, [])
    assert attora_id == _ATTORA_ID
    assert attora_sub == _ATTORA_SUB


def test_extracts_from_nested_parameters_and_custom_field_dict() -> None:
    raw = {
        "tags": [],
        "customFields": {"attora_id": _ATTORA_ID},
        "sources": [
            {
                "type": "dynamic",
                "parameters": {"attora_sub": _ATTORA_SUB},
            },
        ],
    }
    attora_id, attora_sub = _extract_attora_identity(raw, [])
    assert attora_id == _ATTORA_ID
    assert attora_sub == _ATTORA_SUB


def test_tag_prefixes_still_win_when_present() -> None:
    raw = {
        "sources": [{"name": "attora_id", "value": "wrong-id"}],
        "tags": [f"attora_id:{_ATTORA_ID}"],
    }
    attora_id, attora_sub = _extract_attora_identity(
        raw, [t for t in raw["tags"] if isinstance(t, str)]
    )
    assert attora_id == _ATTORA_ID
