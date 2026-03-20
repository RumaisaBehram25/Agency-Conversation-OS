#!/bin/bash
# ============================================
# Attora — Seed Database with Example Data
# ============================================
# Populates product, AI config, and test subscribers
# for an existing Attora account.
#
# Usage:
#   ./scripts/seed-data.sh <api-base-url> <email> <password> <api-key>
#
# Example:
#   ./scripts/seed-data.sh http://34.196.126.130:9000 user@example.com 12345678 atk_abc123...
#   ./scripts/seed-data.sh http://localhost:8000 matt@attora.io attora2026 atk_xyz...
#
# Prerequisites:
#   - API is running and healthy
#   - User account and org already exist
#   - API key (attora_api_key) already generated

set -e

if [ $# -lt 4 ]; then
  echo "Usage: $0 <api-base-url> <email> <password> <api-key>"
  echo ""
  echo "Example:"
  echo "  $0 http://34.196.126.130:9000 user@example.com 12345678 atk_abc123..."
  exit 1
fi

API_BASE="$1"
EMAIL="$2"
PASSWORD="$3"
API_KEY="$4"

echo "============================================"
echo "Attora — Seed Database"
echo "API:   $API_BASE"
echo "User:  $EMAIL"
echo "============================================"

# ── Health Check ────────────────────────────────
echo ""
echo ">>> Health check..."
HEALTH=$(curl -s --max-time 5 "$API_BASE/api/health" 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q "healthy"; then
  echo "    API is healthy"
else
  echo "    ERROR: API is not reachable at $API_BASE"
  echo "    Response: $HEALTH"
  exit 1
fi

# ── Login ───────────────────────────────────────
echo ""
echo ">>> Logging in..."
LOGIN_RESP=$(curl -s --max-time 10 "$API_BASE/api/auth/login" \
  -X POST \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}")

TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
if [ -z "$TOKEN" ]; then
  echo "    ERROR: Failed to get auth token"
  echo "    Response: $LOGIN_RESP"
  exit 1
fi
echo "    Logged in successfully"

AUTH="Authorization: Bearer $TOKEN"

# ── Create Product ──────────────────────────────
echo ""
echo ">>> Creating product (GLP-1 Buddy)..."
PRODUCT_RESP=$(curl -s --max-time 10 "$API_BASE/api/products" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{
    "name": "Dr. Stephanie'\''s GLP-1 Buddy Vitamin + Creatine Drink Mix - 12ct",
    "description": "GLP-1 Buddy is designed to be taken with GLP-1 medications to maximize results and feel your best. This natural formula targets nutritional gaps from GLP-1 medications paired with digestive support so you can enjoy your GLP-1 Journey! Creatine supports lean muscle. Ginger & digestive enzymes provide relief from occasional indigestion, bloating, gas & constipation. Fat soluble vitamins & electrolytes optimize hydration, bone health, energy, and eye health. Collagen peptides support facial skin elasticity while on GLP-1 medications.",
    "price": 29.99,
    "currency": "USD",
    "checkout_url": "https://drstephanies.com/products/glp1-buddy",
    "conversion_value": 29.99,
    "is_active": true,
    "sort_order": 1,
    "eligibility_criteria": {
      "target_audience": "GLP-1 medication users",
      "use_case": "Nutritional supplement to support GLP-1 medication journey"
    },
    "objection_responses": {
      "too_expensive": "GLP-1 Buddy replaces multiple supplements (creatine, collagen, vitamins, electrolytes, digestive enzymes) in one convenient packet — it actually saves money compared to buying each separately.",
      "does_it_work": "Every ingredient is clinically studied at meaningful doses. Dr. Stephanie formulated this based on real-world practitioner experience with GLP-1 patients. Plus, it'\''s 3rd-party tested for purity.",
      "taste": "It'\''s a delicious hydrating drink mix with zero sugar. Most customers say it'\''s the easiest supplement they take all day.",
      "already_taking_vitamins": "Standard multivitamins don'\''t address the specific nutritional gaps caused by GLP-1 medications. GLP-1 Buddy is specifically formulated for the unique needs of GLP-1 users — like collagen for facial skin elasticity and creatine for lean muscle preservation.",
      "side_effects": "GLP-1 Buddy actually helps with common GLP-1 side effects. The ginger and digestive enzymes support relief from occasional indigestion, bloating, gas, and constipation that can come with GLP-1 medications."
    }
  }')

if echo "$PRODUCT_RESP" | grep -q '"id"'; then
  echo "    Product created successfully"
elif echo "$PRODUCT_RESP" | grep -q "already"; then
  echo "    Product may already exist, skipping"
else
  echo "    Response: $PRODUCT_RESP"
fi

# ── Set AI Config ───────────────────────────────
echo ""
echo ">>> Setting AI config..."
AI_RESP=$(curl -s --max-time 10 "$API_BASE/api/ai-config" \
  -X PUT \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d '{
    "brand_voice": "Warm, knowledgeable, and genuinely helpful. Focus on being helpful, not selling. Connect pain points to solutions based on what the product does and its ingredients. For instance, if someone mentions facial skin issues, recommend GLP-1 Buddy because collagen peptides support facial skin elasticity while on GLP-1 medications. Never pressure or hard-sell. Be like a trusted health-savvy friend who happens to know a lot about GLP-1 nutrition.",
    "persona_name": "Dr. Stephanie",
    "product_knowledge": "Dr. Stephanie'\''s GLP-1 Buddy Vitamin + Creatine Drink Mix ($29.99/12ct). Key highlights:\n- WHOLE BODY WELLNESS: Replenishes commonly depleted fat-soluble Vitamins A, D, E, & K to support energy, vision, bone health, & immunity\n- STOMACH & DIGESTIVE AID: Supports balanced bowel movements & helps provide relief for occasional indigestion, bloating, & nausea\n- FACIAL SKIN HEALTH: Collagen peptides support skin firmness and elasticity\n- 5 GRAMS CREATINE, ZERO SUGAR: Clinically meaningful doses. Helps preserve lean muscle during calorie restriction to optimize metabolic health\n- DRINK 1 PACKET DAILY: Delicious, hydrating electrolytes, ZERO sugar\n- DOCTOR-FORMULATED, 3RD PARTY TESTED: Full transparency and multi-stage 3rd-party testing for heavy metals, contaminants & label claim\n\nKey ingredients: Creatine (lean muscle), Ginger & digestive enzymes (digestive relief), Fat-soluble vitamins A/D/E/K & electrolytes (hydration, bone health, energy, eye health), Collagen peptides (facial skin elasticity on GLP-1 medications).",
    "compliance_rules": "ALWAYS include this disclaimer when making any health-related claims: *These statements have not been evaluated by the Food and Drug Administration. This product is not intended to diagnose, treat, cure or prevent any disease.*\n\nNEVER claim the product cures, treats, or prevents any disease. Use language like \"supports\", \"helps with\", \"may provide relief for\". Never make specific medical claims. Never advise someone to stop or change their medication. Always recommend consulting their healthcare provider for medical decisions.",
    "conversion_playbook": "1. Listen first — understand what symptoms or challenges they are experiencing on their GLP-1 journey\n2. Empathize — acknowledge their experience (bloating, muscle loss, skin changes, fatigue are common)\n3. Educate — share relevant ingredient benefits that address their specific concern\n4. Soft recommend — mention GLP-1 Buddy naturally as a solution, not a pitch\n5. Offer to help — provide checkout link only when they express interest\n6. Never push — if they are not interested, wish them well on their GLP-1 journey",
    "objection_handlers": {
      "too_expensive": "GLP-1 Buddy replaces multiple supplements in one convenient packet — creatine, collagen, vitamins, electrolytes, and digestive enzymes. Compared to buying each separately, it actually saves money.",
      "does_it_work": "Every ingredient is clinically studied at meaningful doses. Dr. Stephanie formulated this based on real-world practitioner experience. Plus, it is 3rd-party tested for purity and label accuracy.",
      "already_taking_vitamins": "Standard multivitamins do not address the specific nutritional gaps caused by GLP-1 medications. GLP-1 Buddy targets the unique needs of GLP-1 users — like collagen for skin elasticity and creatine for lean muscle.",
      "not_sure_i_need_it": "Many GLP-1 users do not realize their medications can deplete fat-soluble vitamins and affect muscle mass. GLP-1 Buddy was designed to fill those specific gaps so you can feel your best on your journey."
    },
    "greeting_message": "Hey! Thanks for reaching out. I am Dr. Stephanie — I help people get the most out of their GLP-1 journey. What is going on with you?",
    "fallback_message": "Give me just a moment to look into that for you!",
    "max_messages_before_handoff": 50
  }')

if echo "$AI_RESP" | grep -q '"id"'; then
  echo "    AI config set successfully"
else
  echo "    Response: $AI_RESP"
fi

# ── Send Test Webhook Messages ──────────────────
echo ""
echo ">>> Sending test webhook messages to create subscribers..."

echo "    Subscriber 1: Sarah (digestive issues)..."
S1_RESP=$(curl -s --max-time 30 "$API_BASE/api/manychat/webhook" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-Attora-Key: $API_KEY" \
  -d '{
    "subscriber": {
      "id": "ig_sarah_001",
      "first_name": "Sarah",
      "last_name": "Mitchell",
      "phone": "+15551234567",
      "email": "sarah.m@example.com",
      "custom_fields": {"attora_buyer_stage": "awareness"}
    },
    "last_input_text": "Hi! I just started Ozempic and I have been having really bad bloating and nausea. Is there anything that can help?",
    "channel": "instagram"
  }' 2>/dev/null)
if echo "$S1_RESP" | grep -q "messages"; then
  echo "    Sarah created (AI responded)"
else
  echo "    Sarah response: $S1_RESP"
fi

echo "    Subscriber 2: Mike (muscle loss)..."
S2_RESP=$(curl -s --max-time 30 "$API_BASE/api/manychat/webhook" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-Attora-Key: $API_KEY" \
  -d '{
    "subscriber": {
      "id": "ig_mike_002",
      "first_name": "Mike",
      "last_name": "Torres",
      "phone": "+15559876543",
      "email": "mike.t@example.com",
      "custom_fields": {"attora_buyer_stage": "awareness"}
    },
    "last_input_text": "Hey I saw your post about supplements for Mounjaro users. I have been losing a lot of muscle since I started, is that common?",
    "channel": "instagram"
  }' 2>/dev/null)
if echo "$S2_RESP" | grep -q "messages"; then
  echo "    Mike created (AI responded)"
else
  echo "    Mike response: $S2_RESP"
fi

# ── Summary ─────────────────────────────────────
echo ""
echo "============================================"
echo "Seed complete!"
echo "============================================"
echo "  Product:      GLP-1 Buddy (\$29.99)"
echo "  AI Persona:   Dr. Stephanie"
echo "  Subscribers:  Sarah Mitchell, Mike Torres"
echo "============================================"
