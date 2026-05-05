# Hyros ↔ Attora: URL identity fields (`attora_id`, `attora_sub`)

This document describes how outbound Attora DM links expose lead identity in URL query parameters, what to request from Hyros support, how the Attora backend reads those values from Hyros API payloads, and how to validate the setup end-to-end.

## What to ask Hyros support

Attora stamps every DM / outbound subscriber link with (when values exist):

- `attora_sub` — ManyChat (or platform) subscriber id (string).
- `attora_id` — Attora internal UUID for the subscriber (stable across channels).

Ask Hyros to **capture these from the landing-page URL** and attach them to each lead/sale record in a way Attora’s sync can read, typically one of:

1. **Lead tags** using the prefixes Attora already supports, e.g. `attora_id=<uuid>` and `attora_sub=<manychat_id>`, **or**
2. **Custom fields** named exactly `attora_id` and `attora_sub` (case-insensitive name matching against list-of-`{name, value}` rows is supported).

Ensure the mapped values appear on **both** lead objects and sale objects if purchases are surfaced separately — matching uses purchaser identity extracted from whichever payload shape Hyros returns.

## Expected Hyros API / payload shape after mapping

Attora does not mandate a single Hyros JSON schema; parsers are defensive. Useful shapes include:

- **Tags**: `tags: ["...", "attora_id:550e8400-e29b-41d4-a716-446655440000", "attora_sub:12345", ...]`
- **Custom fields dictionary**: `customFields: { "attora_id": "...", "attora_sub": "..." }`
- **Custom fields list**: `custom_fields: [{"name": "attora_id", "value": "..."}, {"name": "attora_sub", "value": "..."}]`

Values may also appear duplicated on nested `lead`/`sale` objects depending on Hyros’ export shape; `_extract_attora_identity` merges tags + custom-field conventions.

## How `_extract_attora_identity` consumes it

Implementation: `backend/app/services/hyros_service.py`.

The function `_extract_attora_identity(raw: dict, tags: list[str]) -> tuple[str | None, str | None]`:

1. **Scans tags** for known prefixes (`attora_id=`, `attora_id:`, `attora_sub=`, `attora_sub:`, including `attora-id` hyphen variants).
2. **Scans `raw`** for `customFields` / `custom_fields` / `customField` / `fields` which are either:
   - a dict with keys `attora_id` / `attoraId` and `attora_sub` / `attoraSub`, or
   - a list of `{name, value}` entries where `name` matches `attora_id` / `attora_sub`.
3. Returns `(attora_id, attora_sub)` with **`None`** for anything not found — never synthesized.

These values populate `HyrosLead.attora_id` / `HyrosLead.attora_sub` and sale-side extraction for purchase matching (`attora_sub` / `attora_id` matching paths).

## End-to-end test plan (after Hyros confirms mapping)

1. **Outbound link**: From an Attora org with a configured campaign UTMs, trigger a DM (or `/api/campaigns/{id}/utm-for-subscriber?id=`) and verify the URL includes `utm_medium=dm`, `utm_source`, `utm_campaign`, and when applicable `attora_sub` / `attora_id`.
2. **Click through**: Land on the merchant storefront with those query params present (or persisted via storefront attribution bridge).
3. **Hyros side**: Confirm a new/test lead shows the same `attora_id` / `attora_sub` in tags or custom fields as mapped.
4. **Attora sync**: Run or wait for Hyros sync; confirm `HyrosLeadMatch` can align the subscriber via `matched_by` `attora_sub` or `attora_id` in logs / settings UI counters.
5. **Regression**: No change required to sync **cadence** or **matching order** once fields are visible in payloads — parsers already prefer explicit identity fields when present.
