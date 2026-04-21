#!/bin/bash
# ============================================
# Attora — Campaign + UTM + Compliance Test Flow
# ============================================
# End-to-end test WITHOUT a real Instagram account. Simulates:
#   1. Register an Attora-managed campaign with a fake meta_campaign_id
#   2. Generate the 3 UTM URLs (product / checkout / success)
#   3. Fire a ManyChat webhook tagged with that campaign_id
#        → expect subscriber linked to the campaign (attora_campaign_id set)
#   4. Fire a ManyChat webhook with an UNREGISTERED campaign_id
#        → expect a COMPLIANCE warning in the API logs (still processed, not blocked)
#
# Usage:
#   ./scripts/test-campaign-flow.sh <api-base-url> <email> <password> <api-key>
#
# Example:
#   ./scripts/test-campaign-flow.sh http://localhost:8000 matt@attora.io attora2026 atk_xyz...
#
# Prerequisites:
#   - API running and healthy
#   - User account + org exist
#   - API key (atk_...) generated for the org
#   - A product already exists (run seed-data.sh first if needed)
#   - `jq` installed (for pretty JSON + field extraction)
#
# After this script runs, tail the API logs to see the compliance warning:
#   docker compose logs -f backend | grep COMPLIANCE

set -e

if [ $# -lt 4 ]; then
  echo "Usage: $0 <api-base-url> <email> <password> <api-key>"
  exit 1
fi

API_BASE="$1"
EMAIL="$2"
PASSWORD="$3"
API_KEY="$4"

# Fake Meta IDs — not real, just strings the DB will store and match against
REGISTERED_CAMPAIGN_ID="test_camp_$(date +%s)"
UNREGISTERED_CAMPAIGN_ID="rogue_camp_999"

echo "============================================"
echo "Attora — Campaign + UTM Test Flow"
echo "API:                    $API_BASE"
echo "Registered campaign:    $REGISTERED_CAMPAIGN_ID"
echo "Unregistered campaign:  $UNREGISTERED_CAMPAIGN_ID  (used to test compliance guard)"
echo "============================================"

# Require jq
if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required. Install via: apt-get install jq (or brew install jq)"
  exit 1
fi

# ── Health ──────────────────────────────────────
echo ""
echo ">>> [0/6] Health check"
HEALTH=$(curl -s --max-time 5 "$API_BASE/api/health" || echo "FAIL")
echo "$HEALTH" | grep -q "healthy" || { echo "    API not reachable: $HEALTH"; exit 1; }
echo "    OK"

# ── Login ───────────────────────────────────────
echo ""
echo ">>> [1/6] Login"
TOKEN=$(curl -s --max-time 10 "$API_BASE/api/auth/login" \
  -X POST -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | jq -r '.access_token')
[ -n "$TOKEN" ] && [ "$TOKEN" != "null" ] || { echo "    Login failed"; exit 1; }
AUTH="Authorization: Bearer $TOKEN"
echo "    OK"

# ── Create campaign ─────────────────────────────
echo ""
echo ">>> [2/6] POST /api/campaigns — register Attora-managed campaign"
CAMPAIGN_RESP=$(curl -s --max-time 10 "$API_BASE/api/campaigns" \
  -X POST -H "Content-Type: application/json" -H "$AUTH" \
  -d "{
    \"name\": \"Test GLP-1 Buddy Campaign $(date +%H%M%S)\",
    \"description\": \"Synthetic campaign for local e2e test\",
    \"meta_campaign_id\": \"$REGISTERED_CAMPAIGN_ID\",
    \"meta_ad_set_id\": \"test_adset_1\",
    \"is_attora_managed\": true,
    \"is_active\": true
  }")

CAMPAIGN_ID=$(echo "$CAMPAIGN_RESP" | jq -r '.id')
[ -n "$CAMPAIGN_ID" ] && [ "$CAMPAIGN_ID" != "null" ] || {
  echo "    Campaign create failed:"; echo "$CAMPAIGN_RESP" | jq .; exit 1; }
echo "    Campaign id: $CAMPAIGN_ID"

# ── Generate UTMs ───────────────────────────────
echo ""
echo ">>> [3/6] POST /api/campaigns/$CAMPAIGN_ID/generate-utms"
UTM_RESP=$(curl -s --max-time 10 "$API_BASE/api/campaigns/$CAMPAIGN_ID/generate-utms" \
  -X POST -H "Content-Type: application/json" -H "$AUTH" \
  -d '{
    "product_page_url":  "https://drstephanies.com/products/glp1-buddy",
    "checkout_url":      "https://drstephanies.com/checkouts/glp1-buddy",
    "success_url":       "https://drstephanies.com/pages/thank-you",
    "utm_source":        "attora",
    "utm_medium":        "messaging"
  }')

echo "$UTM_RESP" | jq -e '.product_page_utm_url' >/dev/null || {
  echo "    UTM generate failed:"; echo "$UTM_RESP" | jq .; exit 1; }

echo "    Product UTM:   $(echo "$UTM_RESP" | jq -r '.product_page_utm_url')"
echo "    Checkout UTM:  $(echo "$UTM_RESP" | jq -r '.checkout_utm_url')"
echo "    Success UTM:   $(echo "$UTM_RESP" | jq -r '.success_utm_url')"

# ── Webhook: matched campaign ───────────────────
echo ""
echo ">>> [4/6] Simulate ManyChat webhook — REGISTERED campaign_id"
echo "    (expect: subscriber created, attora_campaign_id set, no compliance warning)"
SUB1_ID="ig_test_match_$(date +%s)"
W1_RESP=$(curl -s --max-time 30 "$API_BASE/api/manychat/webhook" \
  -X POST -H "Content-Type: application/json" -H "X-Attora-Key: $API_KEY" \
  -d "{
    \"subscriber\": {
      \"id\": \"$SUB1_ID\",
      \"first_name\": \"MatchedLead\",
      \"last_name\": \"Test\",
      \"custom_fields\": {
        \"campaign_id\": \"$REGISTERED_CAMPAIGN_ID\",
        \"ad_id\": \"test_ad_1\",
        \"ad_set_id\": \"test_adset_1\"
      }
    },
    \"last_input_text\": \"I saw your ad about GLP-1 support, tell me more\",
    \"channel\": \"instagram\"
  }")
echo "    Webhook returned:"; echo "$W1_RESP" | jq '{reply_count: (.content.messages | length), reply_preview: (.content.messages[0].text // "<none>" | .[0:120]), actions: (.content.actions | length), quick_replies: (.content.quick_replies | length)}' 2>/dev/null || echo "$W1_RESP"

# ── Webhook: unregistered campaign (compliance path) ─
echo ""
echo ">>> [5/6] Simulate ManyChat webhook — UNREGISTERED campaign_id"
echo "    (expect: COMPLIANCE warning in backend logs, subscriber has no attora_campaign_id)"
SUB2_ID="ig_test_rogue_$(date +%s)"
W2_RESP=$(curl -s --max-time 30 "$API_BASE/api/manychat/webhook" \
  -X POST -H "Content-Type: application/json" -H "X-Attora-Key: $API_KEY" \
  -d "{
    \"subscriber\": {
      \"id\": \"$SUB2_ID\",
      \"first_name\": \"RogueLead\",
      \"last_name\": \"Test\",
      \"custom_fields\": {
        \"campaign_id\": \"$UNREGISTERED_CAMPAIGN_ID\"
      }
    },
    \"last_input_text\": \"hello from an unregistered campaign\",
    \"channel\": \"instagram\"
  }")
echo "    Webhook returned:"; echo "$W2_RESP" | jq '{reply_count: (.content.messages | length), reply_preview: (.content.messages[0].text // "<none>" | .[0:120])}' 2>/dev/null || echo "$W2_RESP"

# ── Verify via API ──────────────────────────────
echo ""
echo ">>> [6/6] Verify — GET /api/campaigns (confirm campaign + UTM persisted)"
curl -s --max-time 10 "$API_BASE/api/campaigns?is_attora_managed=true" -H "$AUTH" \
  | jq "[.[] | select(.meta_campaign_id == \"$REGISTERED_CAMPAIGN_ID\") | {id, name, meta_campaign_id, is_attora_managed, utm: (.utm | {utm_campaign, product_page_utm_url, checkout_utm_url, success_utm_url})}]"

echo ""
echo "============================================"
echo "Done."
echo ""
echo "Next — verify subscriber linkage + compliance log:"
echo ""
echo "  1. Compliance warning (should show rogue_camp_999):"
echo "       docker compose logs --tail=200 backend | grep COMPLIANCE"
echo ""
echo "  2. Subscriber <-> campaign link (from DB):"
echo "       docker compose exec postgres psql -U attora -d attora -c \\"
echo "         \"SELECT manychat_subscriber_id, campaign_id, attora_campaign_id \\"
echo "          FROM subscribers \\"
echo "          WHERE manychat_subscriber_id IN ('$SUB1_ID','$SUB2_ID');\""
echo ""
echo "     Expected: $SUB1_ID has attora_campaign_id SET; $SUB2_ID has it NULL."
echo "============================================"
