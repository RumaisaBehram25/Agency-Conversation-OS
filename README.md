# Attora

White-labeled ManyChat platform with an AI conversation engine and Revenue Activation System (RAS) dashboard. Attora plugs into ManyChat via the External Request action, classifies subscriber intent with Claude Haiku, generates contextual sales responses with Claude Sonnet, and feeds conversion data back to Meta ads through the Conversions API.

**Production capabilities today:**

- **Campaigns & DM links** — per-org campaigns with UTM funnel URLs stamped with `attora_sub` (ManyChat id) and `attora_id` (Attora UUID) on every outbound link
- **Hyros** — periodic purchase sync; match leads by `attora_id` → `attora_sub` → email; suppress follow-ups when purchased
- **Follow-ups** — timed nudge sequences per campaign; Attora decides when to send; ManyChat delivers via `manychat_outbound_flow_ns`
- **Storefront tracking** — `POST /api/conversions/track` for lead / initiate_checkout / purchase (+ optional Meta CAPI)
- **Analytics** — Meta ad spend sync, organic vs paid breakdown, Hyros purchase metrics in the dashboard

## Architecture

```
┌──────────────┐     ┌──────────────────────────────────────────────────────────┐
│              │     │  Docker Compose                                          │
│   ManyChat   │     │                                                          │
│  (External   │────▶│  ┌─────────┐    ┌───────────┐    ┌────────────────────┐  │
│   Request)   │◀────│  │  nginx   │───▶│  FastAPI   │───▶│  PostgreSQL 16     │  │
│              │     │  │  :3000   │    │  :8000    │    │  :5432             │  │
└──────────────┘     │  └─────────┘    └─────┬─────┘    └────────────────────┘  │
                     │       │               │                                  │
┌──────────────┐     │  React SPA        ┌───┴───┐      ┌────────────────────┐  │
│   Meta Ads   │◀────│  Dashboard        │Redis 7│      │  Claude API        │  │
│  (CAPI)      │     │                   │ :6379 │      │  Haiku + Sonnet    │  │
└──────────────┘     │                   └───────┘      └────────────────────┘  │
                     └──────────────────────────────────────────────────────────┘

**External integrations:** ManyChat (webhook + outbound flows), Meta Marketing API (ad spend) + CAPI (conversions), Hyros (purchase attribution), Anthropic Claude (AI pipeline), optional S3/Trino OLAP lake.
```

**Four Docker services:**

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `api` | Python 3.12 / uvicorn | 8000 | FastAPI backend |
| `frontend` | nginx 1.27-alpine | 3000 | React SPA + reverse proxy |
| `postgres` | postgres:16-alpine | 5432 | Primary database |
| `redis` | redis:7-alpine | 6379 | Cache, rate limiting, session context |

nginx serves the React build at `/` and proxies `/api/*` requests to the FastAPI backend.

**Optional Docker profiles:**

| Profile | Service | Purpose |
|---------|---------|---------|
| `olap-selfhosted` | `scheduler` + MinIO + Trino | OLAP exports, archives, parity checks |
| `hyros-scheduler` | `hyros-scheduler` | Hyros purchase sync + follow-up dispatch (no OLAP stack) |

```bash
# Hyros sync (every 3h) + follow-ups (every 15m) — set env flags in .env first
docker compose --profile hyros-scheduler up -d hyros-scheduler
```

Requires `HYROS_SYNC_SCHEDULER_ENABLED=true` and/or `FOLLOW_UP_SCHEDULER_ENABLED=true`, plus org-level `manychat_outbound_flow_ns` for follow-ups to actually send.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- An Anthropic API key (`sk-ant-...`)
- Node.js 20+ (for local frontend dev only)

### 1. Clone and configure

```bash
git clone <repo-url> attora && cd attora
cp .env.example .env
```

Edit `.env` and set **three required secrets**:

```bash
# Generate a JWT secret (any random 32+ char string)
JWT_SECRET_KEY=your-random-jwt-secret-at-least-32-chars

# Generate a Fernet encryption key
ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Your Anthropic API key
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### 2. Start the stack

```bash
docker-compose up --build
```

This starts all four services. Postgres and Redis include health checks — the API waits for both to be healthy before starting.

### Optional: start the self-hosted OLAP profile

Phase 1 keeps the existing UI and API behavior unchanged, but the backend can now be configured with an OLAP object store for parallel exports and parity checks.

```bash
docker-compose --profile olap-selfhosted up --build
```

With the self-hosted profile enabled, MinIO is exposed at `http://localhost:9002` and the S3-compatible API is exposed at `http://localhost:9001`.

Set these env values in `.env` when using the self-hosted profile:

```bash
OLAP_STORAGE_PROVIDER=s3
OLAP_QUERY_PROVIDER=trino
OLAP_BUCKET=attora-analytics
OLAP_PREFIX=lake
OLAP_ENDPOINT=http://minio:9000
OLAP_ACCESS_KEY_ID=minioadmin
OLAP_SECRET_ACCESS_KEY=minioadmin
OLAP_S3_FORCE_PATH_STYLE=true
OLAP_SECURE=false
OLAP_SCHEDULER_ENABLED=true
TRINO_HOST=trino
TRINO_PORT=8080
TRINO_HOST_PORT=8083
TRINO_USER=attora
TRINO_CATALOG=lakehouse
TRINO_SCHEMA=default
```

Later, the same backend code can be pointed at AWS by changing the same env contract to S3 and Athena values.

The self-hosted profile now includes a scheduler container that runs phase 1 OLAP maintenance jobs from env-configured cron expressions. By default it exports `daily_analytics` and `ai_usage_events`, shadow-archives old messages in 7-day windows, and runs both low-level dataset parity and reporting parity checks by org/date range.

The same profile now also starts a Hive metastore and Trino. Existing `/api/*` routes remain PostgreSQL-backed and are the stable frontend path. Additive Trino-backed mirrors are available under `/api/olap/*` with the same response formats for dashboard, analytics, ROI, AI performance, exports, and campaign drill-downs.

Frontend guidance:

- Use `/api/dashboard`, `/api/analytics*`, and `/api/campaigns*` for the current production UI flow.
- Use `/api/olap/*` only for experimental or side-by-side OLAP validation flows.
- There is no longer a root-route toggle for switching `/api/*` to OLAP; OLAP access is isolated under `/api/olap/*`.

There is also a manual trigger endpoint for OLAP maintenance jobs at `POST /api/olap/jobs/trigger`. Supported jobs are `export_daily_analytics`, `export_ai_usage`, `archive_messages`, `check_olap_parity`, and `check_reporting_parity`.

Trino is published on `http://localhost:8083` by default to avoid collisions with other local services. The application still connects to Trino internally with `TRINO_HOST=trino` and `TRINO_PORT=8080`.

Checkpoint metadata is stored in object storage under the configured checkpoint prefix, so scheduled exports and archives process delta windows instead of rescanning full historical partitions on every run.

### 3. Run the database migration

```bash
docker-compose exec api alembic upgrade head
```

This applies all Alembic migrations (campaigns, Hyros fields, follow-up workflow, email queue, playbook seeds, etc.).

### 4. Seed the knowledge base

The seed script and PDF live outside the `backend/` build context, so copy them into the running `api` container first, then run. `psycopg2-binary` is needed because the script uses the sync SQLAlchemy driver.

```bash
docker cp scripts/seed_knowledge.py attora-api-1:/seed.py
docker cp Overcome7Objections.pdf attora-api-1:/Overcome7Objections.pdf
docker-compose exec api pip install psycopg2-binary
docker-compose exec api python /seed.py
```

This parses `Overcome7Objections.pdf` into ~37 chunked documents with keyword tags and inserts them into the `knowledge_documents` table. The script is idempotent — safe to re-run.

### 5. Access the app

- **Dashboard**: http://localhost:3000
- **API docs** (dev mode): http://localhost:8000/api/docs
- **Health check**: http://localhost:8000/api/health

## Multi-Tenant Data Model

Attora uses a single Postgres database with application-layer tenant isolation. Every org-scoped table has an `org_id` foreign key, and all queries filter on it.

```
users ─────┐
           │ many-to-many
org_users ─┤
           │
organizations ──┬── products
                ├── ad_campaigns ─── campaign_utms
                │              └── campaign_follow_ups
                ├── ai_config (one per org)
                ├── subscribers ──── conversations ──── messages
                ├── conversion_events
                ├── hyros_sync_logs
                ├── manychat_events
                ├── email_queue / email_log
                └── daily_analytics (+ campaign_metrics)
```

### Key tables

| Table | Purpose |
|-------|---------|
| `organizations` | Tenant. ManyChat + Meta credentials, `attora_api_key`, optional `manychat_outbound_flow_ns` for follow-up delivery (Fernet-encrypted secrets). |
| `users` / `org_users` | Users belong to orgs via a join table with roles: `owner`, `admin`, `member`, `viewer`. |
| `products` | Product catalog per org (price, checkout URLs, conversion value, objection responses). |
| `ad_campaigns` | Registered campaigns (paid Meta id or organic `keyword`). Links to a product and optional `conversation_script`. |
| `campaign_utms` | Funnel URLs with baked-in `utm_*`; per-subscriber URLs add `attora_sub`, `attora_id`, `utm_medium=dm`. |
| `campaign_follow_ups` | Per-campaign nudge sequence (`step_order`, `after_minutes`, message with optional `[LINK]`). |
| `ai_config` | Per-org AI tuning: brand voice, persona, compliance rules, conversion playbook, objection handlers. |
| `subscribers` | ManyChat mirror + buyer stage, UTMs, Hyros purchase flags, `attora_campaign_id`, `last_user_message_at` (follow-up silence anchor). |
| `conversations` | Sessions with `follow_up_attempts`, `last_follow_up_at`, status, message counts. |
| `messages` | Messages with AI metadata; `is_follow_up` distinguishes nudges from live AI replies. |
| `conversion_events` | Storefront/CAPI events: `lead`, `initiate_checkout`, `purchase`, `upsell`. |
| `hyros_sync_logs` | Per-org sync run stats (match rate, matched_by attora_id / attora_sub / email). |
| `daily_analytics` | Pre-aggregated daily metrics. Populated by `daily_digest` + ad spend sync. |

### Per-Org Credentials

Each organization stores its own platform credentials:

**ManyChat**: `manychat_api_key`, `manychat_page_id`, `manychat_account_id`
**Meta**: `meta_pixel_id`, `meta_capi_token`, `meta_ad_account_id`, `meta_page_id`, `meta_business_manager_id`
**Attora**: `attora_api_key` (used for webhook authentication)

All API keys and tokens are encrypted at rest with Fernet symmetric encryption and masked in API responses (e.g., `****abc123`).

## AI Conversation Engine

The engine runs as an 8-step pipeline with a hard 10-second time budget (matching ManyChat's External Request timeout).

```
ManyChat webhook
    │
    ▼
┌─ Step 1: Load org config ─────────── <100ms (Redis cache, 5-min TTL)
│
├─ Step 2: Load conversation context ─ <200ms (subscriber + last 10 messages)
│
├─ Step 3: Classify intent ─────────── <500ms (Claude Haiku)
│     │
│     ├─ greeting/spam/off_topic → cached response (skip to Step 7)
│     │
│     ▼
├─ Step 4: Route
│
├─ Step 5: Generate response ───────── <7000ms (Claude Sonnet)
│
├─ Step 6: Validate output ─────────── <50ms (4-layer defense)
│
├─ Step 7: Fire-and-forget ─────────── async (store message, CAPI, summarize)
│
└─ Return ManyChat v2 response
```

### Intent Classification (Haiku)

Classifies each message into one of 8 intents: `question`, `objection`, `purchase_intent`, `browsing`, `support`, `off_topic`, `greeting`, `spam`. Also detects language (ISO 639-1), sentiment (positive/neutral/negative), and whether the intent is simple enough for a cached response.

Simple intents (greeting, spam, off_topic) are routed to pre-written fallback responses and skip the Sonnet call entirely, saving cost and latency.

### Response Generation (Sonnet)

Builds a system prompt from the org's AI config (brand voice, persona, product knowledge, compliance rules, conversion playbook) with Anthropic `cache_control` blocks to reduce token costs. Generates a structured JSON response including the reply text, buyer stage assessment, quick reply suggestions, and conversion readiness signal.

### Hallucination Defense (4 layers)

1. **Banned phrases** — regex scan for medical claims, guarantees, diagnosis language
2. **Price validation** — any price mentioned must match the product catalog exactly
3. **Compliance flags** — tags responses that reference sensitive topics
4. **Kill switch** — immediately hands off to a human for adverse reactions, billing disputes, legal threats, self-harm mentions, or minor involvement

If any layer fails, the response text is cleaned or replaced and compliance flags are attached.

### Buyer Stage Engine

Tracks subscribers through a forward-only funnel:

```
awareness → consideration → intent → purchase → post_purchase
```

Stage transitions are detected from intent signals, keyword patterns, and AI assessment. The stage is persisted on the subscriber record and passed back to ManyChat as a custom field for flow routing.

### Context Management

- Loads last 10 messages from Redis (10-min TTL) with Postgres fallback
- Every 4 conversation turns, fires an async Haiku summarization to compress context
- Stores new messages and updates subscriber/conversation records via fire-and-forget tasks
- Fires Meta CAPI conversion events asynchronously when conversion readiness is detected

## ManyChat Integration

### Webhook Setup

In ManyChat, create an External Request action pointing to:

```
POST https://your-domain.com/api/manychat/webhook
```

**Headers:**
```
X-Attora-Key: <your org's attora_api_key>
Content-Type: application/json
```

The webhook authenticates via `X-Attora-Key` (not JWT). Each org gets a unique API key generated at org creation, stored encrypted in the database, and cached in Redis for fast lookups.

### Request/Response Format

**Request** (from ManyChat):
```json
{
  "subscriber": {
    "id": "12345",
    "first_name": "Jane",
    "last_name": "Doe",
    "phone": "+15551234567",
    "email": "jane@example.com",
    "custom_fields": {
      "attora_buyer_stage": "consideration",
      "ctwa_clid": "abc123",
      "ad_id": "456",
      "ad_set_id": "789",
      "campaign_id": "012"
    }
  },
  "last_input_text": "How much does the starter plan cost?",
  "channel": "instagram",
  "keyword": "MUSCLE",
  "attora_campaign_id": "uuid-of-ad_campaign",
  "flow_id": "manychat-flow-ns"
}
```

**ManyChat flow tips:**

- First External Request after welcome DM: hardcode `"Send me the link"` as `last_input_text` (not `{{attora_last_input}}`).
- Loop External Request: use ManyChat's **Last Input Text** system field for `last_input_text`.
- Outbound follow-up flow: trigger tag `xattora_never_fires_x`; send `{{cuf_attora_outbound_message}}` (set by Attora via ManyChat API before each nudge).
- ManyChat v2 responses can include `content.messages[]` — you may omit a separate Send Message node if the webhook returns text.

**Response** (ManyChat v2 format):
```json
{
  "version": "v2",
  "content": {
    "messages": [
      { "type": "text", "text": "Great question! The Starter plan is $49/month..." }
    ],
    "actions": [
      { "action": "set_field_value", "field_name": "attora_buyer_stage", "value": "intent" }
    ],
    "quick_replies": [
      { "type": "node", "caption": "See pricing details" },
      { "type": "node", "caption": "Talk to sales" }
    ]
  }
}
```

## Campaigns & DM Attribution

Campaigns tie a product to a keyword (organic) or Meta ad campaign id (paid). Each campaign has one or more **funnel URLs** (`campaign_utms`) with `utm_source`, `utm_medium`, `utm_campaign`, etc.

When the AI sends a checkout or funnel link, `build_dm_link()` appends per-subscriber params:

| Param | Meaning |
|-------|---------|
| `attora_sub` | ManyChat subscriber id |
| `attora_id` | Attora subscriber UUID |
| `utm_medium` | `dm` (overrides funnel default for DM context) |

Example DM link:

```
https://shop.example.com/macros?utm_campaign=eat-more-transformation-macros&utm_source=attora&utm_medium=dm&attora_id=ad1df68d-...&attora_sub=1748217985
```

**API:** `/api/campaigns` (CRUD), `/api/campaign-metrics` (aggregated spend/conversion facts).

**Dashboard:** `/campaigns` — manage campaigns and UTM rows.

## Hyros Purchase Sync

Organizations store a per-tenant `hyros_api_key`. The sync job pulls recent Hyros sales and matches them to subscribers:

1. `attora_id` (Attora UUID in Hyros lead source)
2. `attora_sub` (ManyChat id)
3. Email fallback

On match, the subscriber is marked purchased, follow-ups are suppressed, and conversion metrics feed analytics.

**Cron:** `POST /api/cron/hyros-sync` (or enable `HYROS_SYNC_SCHEDULER_ENABLED=true` on the `hyros-scheduler` container; default cron every **3 hours**).

**Hyros account setup:** URL rules must capture `attora_id` and `attora_sub` from landing URLs. Rule **order** matters — first-touch attribution is configured in Hyros, not in Attora code.

See `docs/hyros_attora_id_mapping.md` for field mapping details.

## Follow-Up Nudges

Silent leads (no user message after the AI link) receive timed nudges per `campaign_follow_ups`:

| Campaign | Typical cadence |
|----------|-----------------|
| MUSCLE | 60m, 3h, 12h (3 touches) |
| MACROS | 60m, 3h, 12h, 24h (4 touches) |

**How it works:**

1. Attora `follow_up_engine` finds eligible conversations (`last_user_message_at` anchor, not purchased, under max attempts).
2. Writes message text to ManyChat custom field `attora_outbound_message`.
3. Triggers the org's `manychat_outbound_flow_ns` outbound flow (Human Agent tag window — not the 24h messaging window).

**Cron:** `POST /api/cron/follow-ups` with optional `?dry_run=true` (or `FOLLOW_UP_SCHEDULER_ENABLED=true` on `hyros-scheduler`).

**One-time setup:**

```bash
# Seed MUSCLE/MACROS sequences (run against prod DB)
python scripts/seed_warrior_babe_followups.py

# Set org.manychat_outbound_flow_ns in DB or via settings API
```

## Storefront Conversions

Merchant checkout pages POST events to Attora (no JWT — uses org context from attribution params):

```
POST /api/conversions/track
```

| `conversion_type` | Use |
|-------------------|-----|
| `lead` | Email/opt-in captured |
| `initiate_checkout` | Checkout started |
| `purchase` | Order completed |

Include `attora_sub`, `attora_id`, and UTMs in the body. Optionally fires Meta CAPI when org credentials are set.

**Client script:** `docs/storefront-attribution.js` — captures URL params into `localStorage` and re-appends them to checkout links. Drop in product/funnel pages; thank-you page should still POST to `/api/conversions/track`.

## Meta Conversions API

When the AI detects a subscriber is conversion-ready, Attora fires a server-side event to Meta's Conversions API for ad attribution. Supported events:

| Event | Trigger |
|-------|---------|
| `Lead` | Subscriber shows purchase intent |
| `InitiateCheckout` | Subscriber clicks checkout link |
| `Purchase` | Conversion confirmed |

Events are fired asynchronously (fire-and-forget) so they don't block the webhook response. Requires `meta_pixel_id` and `meta_capi_token` configured on the organization.

## Dashboard API

All dashboard endpoints require JWT authentication (Bearer token).

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Create account |
| `/api/auth/login` | POST | Get access + refresh tokens |
| `/api/auth/refresh` | POST | Refresh access token |
| `/api/auth/me` | GET | Current user profile |

Access tokens expire in 30 minutes. Refresh tokens last 7 days. The frontend automatically refreshes expired tokens and queues failed requests for retry.

### Organizations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/organizations` | POST | Create org (auto-generates encrypted API key) |
| `/api/organizations/{id}` | GET | Get org details (sensitive fields masked) |
| `/api/organizations/{id}` | PUT | Update org (owner/admin, encrypts secrets) |
| `/api/organizations/{id}/rotate-key` | POST | Rotate API key (owner only) |

### Products

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/products` | GET | List org products |
| `/api/products` | POST | Create product |
| `/api/products/{id}` | GET | Get product |
| `/api/products/{id}` | PUT | Update product |
| `/api/products/{id}` | DELETE | Delete product |

### AI Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ai-config` | GET | Get config (returns defaults if none set) |
| `/api/ai-config` | PUT | Upsert AI config |

Configurable fields: `brand_voice`, `persona_name`, `product_knowledge`, `compliance_rules`, `conversion_playbook`, `objection_handlers` (key-value map), `greeting_message`, `fallback_message`, `max_messages_before_handoff`.

### Conversations & Leads

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/conversations` | GET | Paginated list (filter by status, channel, date range) |
| `/api/conversations/{id}` | GET | Full conversation with all messages |
| `/api/subscribers` | GET | Paginated list (filter by buyer stage, channel, conversion status) |
| `/api/subscribers/{id}` | GET | Subscriber detail with all conversations |

### Analytics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analytics` | GET | CPQC, CCR, funnel, trends |
| `/api/analytics/roi` | GET | Ad spend, CPA, ROAS, revenue |
| `/api/analytics/ai-performance` | GET | Fallback rate, response time, token cost |
| `/api/analytics/export` | GET | CSV export of daily metrics |

### Dashboard

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard` | GET | Single overview: CPQC trend, CCR trend, active conversations, today's conversions/revenue, campaign health |

### Settings

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/settings` | GET | Org settings (API keys masked) |
| `/api/settings` | PUT | Update settings (owner/admin, encrypts secrets on save) |

### Campaigns

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/campaigns` | GET/POST | List / create campaigns |
| `/api/campaigns/{id}` | GET/PUT/DELETE | Campaign CRUD |
| `/api/campaigns/{id}/utms` | GET/POST | Funnel UTM rows |
| `/api/campaign-metrics` | GET | Campaign-level spend and conversion metrics |

### Conversions (storefront)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/conversions/track` | POST | Attribution params | Record lead / initiate_checkout / purchase |

### AI test / Playground

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ai-test/chat` | POST | Dry-run AI pipeline (dashboard Playground) |

### Emails

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/emails/*` | varies | Email queue dispatch (when org email settings enabled) |

### Cron Jobs

All cron routes require header `X-Cron-Secret: <CRON_SECRET>`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/cron/stale-conversations` | POST | Mark conversations inactive >24h as stale |
| `/api/cron/daily-digest` | POST | Aggregate into `daily_analytics` |
| `/api/cron/ad-spend-sync` | POST | Pull Meta ad spend; dual-write campaign metrics |
| `/api/cron/hyros-sync` | POST | Sync Hyros purchases onto subscribers |
| `/api/cron/follow-ups` | POST | Dispatch due follow-up nudges (`?dry_run=true` for dry run) |
| `/api/cron/export-ai-usage` | POST | Export AI usage events to OLAP |
| `/api/cron/archive-messages` | POST | Archive old messages to OLAP |
| `/api/cron/check-olap-parity` | POST | PostgreSQL vs Parquet parity check |

**Self-hosted schedulers** (`backend/app/jobs/scheduler.py`):

| Env flag | Default cron | Job |
|----------|--------------|-----|
| `OLAP_SCHEDULER_ENABLED` | nightly | OLAP exports, archives, parity |
| `HYROS_SYNC_SCHEDULER_ENABLED` | `0 */3 * * *` | Hyros sync |
| `FOLLOW_UP_SCHEDULER_ENABLED` | `*/15 * * * *` | Follow-up dispatch |

Run via `docker compose --profile hyros-scheduler up hyros-scheduler` or call HTTP cron endpoints from an external scheduler (EventBridge, cron, etc.).

## React Dashboard

Single-page app built with React 18, TypeScript, Tailwind CSS 3, and Vite. Served by nginx in production.

### Pages

| Route | Page | Description |
|-------|------|-------------|
| `/login` | Login | Email/password authentication |
| `/dashboard` | Dashboard | CPQC, CCR, active conversations, conversions, revenue, campaign health indicators |
| `/conversations` | Conversations | Filterable conversation list with status badges |
| `/conversations/:id` | Conversation Detail | Chat-style message view with AI metadata |
| `/leads` | Leads | Subscriber list with buyer stage and conversion filters |
| `/leads/:id` | Lead Detail | Full subscriber profile with conversation history |
| `/products` | Products | Product catalog management with modal forms |
| `/campaigns` | Campaigns | Campaign + UTM funnel URL management |
| `/analytics` | Analytics | Funnel chart, trend lines, ROI waterfall, source breakdown |
| `/playground` | Playground | Live AI pipeline test against org config |
| `/settings` | Settings | Organization credentials (masked), key rotation |

> **Note:** `AIConfigPage.tsx` exists in the codebase but is not wired in `App.tsx` today — AI config is editable via `PUT /api/ai-config` or DB seeds/migrations.

### Key Components

- **Sidebar** — navigation (dashboard, conversations, leads, products, campaigns, analytics, playground, settings)
- **MetricCard** — Displays KPI with sparkline trend and color-coded change indicator
- **CampaignHealth** — Traffic light system (green/yellow/red) for campaign status
- **MessageBubble** — Chat-style bubbles distinguishing user, AI, and human messages
- **FunnelChart** — Buyer stage funnel visualization (Recharts)
- **ROIWaterfall** — Before/after ROI comparison chart
- **ObjectionHandlerEditor** — Key-value pair editor for AI objection responses

### Auth Flow

1. User logs in, receives `access_token` + `refresh_token` stored in localStorage
2. Axios interceptor attaches `Authorization: Bearer <token>` to every request
3. On 401, the interceptor queues the failed request, refreshes the token via `/api/auth/refresh`, and retries all queued requests
4. Failed refresh clears storage and redirects to `/login`

## Security

### Encryption at Rest

Sensitive fields are encrypted with Fernet symmetric encryption before database storage:
- `manychat_api_key`
- `meta_capi_token`
- `attora_api_key`

The encryption key is loaded from the `ENCRYPTION_KEY` environment variable. Generate one:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Authentication

- **Dashboard**: JWT Bearer tokens (HS256, 30-min access / 7-day refresh)
- **Webhook**: `X-Attora-Key` header matched against encrypted org API keys
- **Cron jobs**: `X-Cron-Secret` header

### Rate Limiting

Redis-backed sliding window — 100 requests per minute per IP address. Health check endpoints are exempt. Fails open if Redis is unavailable.

### nginx Security Headers

```
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

Static assets are cached with `Cache-Control: immutable` (1 year). Gzip compression is enabled for text, JS, JSON, XML, and SVG.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(see `.env.example`)* | Async Postgres connection (`postgresql+asyncpg://...`) |
| `DATABASE_URL_SYNC` | *(see `.env.example`)* | Sync connection for Alembic |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `attora` | Local Docker Postgres credentials |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `JWT_SECRET_KEY` | `change-me-...` | **Must change.** JWT signing secret (32+ chars) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `ENCRYPTION_KEY` | `change-me-...` | **Must change.** Fernet key for field encryption |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed CORS origins (comma-separated) |
| `RATE_LIMIT_PER_MINUTE` | `100` | Max requests per minute per IP |
| `ANTHROPIC_API_KEY` | (empty) | **Required.** Anthropic API key for Claude |
| `WARRIOR_BABE_CALL_LINK` | Warrior Babe schedule URL | Injected into escalation playbook at runtime |
| `CRON_SECRET` | `change-me-...` | Secret for `X-Cron-Secret` on cron routes |
| `HYROS_SYNC_SCHEDULER_ENABLED` | `false` | Enable Hyros sync inside `hyros-scheduler` |
| `HYROS_SYNC_SCHEDULER_CRON` | `0 */3 * * *` | Hyros sync schedule (every 3 hours) |
| `FOLLOW_UP_SCHEDULER_ENABLED` | `false` | Enable follow-up dispatch inside `hyros-scheduler` |
| `FOLLOW_UP_SCHEDULER_CRON` | `*/15 * * * *` | Follow-up cadence (every 15 minutes) |
| `OLAP_SCHEDULER_ENABLED` | `false` | Enable OLAP export/archive jobs |
| `OLAP_*` | various | S3/MinIO lake, Trino, Athena settings (see `.env.example`) |
| `APP_NAME` | `Attora` | Application name |
| `APP_ENV` | `development` | Environment (development/staging/production) |
| `DEBUG` | `true` | When `true`, exposes `/api/docs` |
| `LOG_LEVEL` | `INFO` | Logging level |

Copy `.env.example` to `.env` and replace placeholder secrets. **Do not commit production database URLs or API keys.**

## Tech Stack

### Backend

| Package | Version | Purpose |
|---------|---------|---------|
| FastAPI | 0.115.6 | Web framework |
| uvicorn | 0.34.0 | ASGI server |
| SQLAlchemy | 2.0.36 | Async ORM |
| asyncpg | 0.30.0 | Postgres driver |
| Alembic | 1.14.1 | Migrations |
| Pydantic | 2.10.4 | Validation & settings |
| redis | 5.2.1 | Cache client |
| anthropic | 0.42.0 | Claude API |
| httpx | 0.28.1 | Async HTTP (ManyChat, Meta CAPI) |
| passlib + bcrypt | 1.7.4 / 4.2.1 | Password hashing |
| python-jose | 3.3.0 | JWT encode/decode |
| cryptography | 44.0.0 | Fernet encryption |

### Frontend

| Package | Version | Purpose |
|---------|---------|---------|
| React | 18.3.1 | UI framework |
| React Router | 6.26.2 | Client-side routing |
| Recharts | 2.13.3 | Charts and visualizations |
| Axios | 1.7.7 | HTTP client with interceptors |
| TypeScript | 5.6.3 | Type safety |
| Tailwind CSS | 3.4.13 | Utility-first styling |
| Vite | 5.4.10 | Build tool |

## Project Structure

```
attora/
├── docker-compose.yml
├── .env.example
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── alembic.ini
│   │   └── versions/              # 29+ migrations (campaigns, Hyros, follow-ups, email, …)
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── api/
│       │   ├── manychat_webhook.py
│       │   ├── campaigns.py / campaign_metrics.py
│       │   ├── conversions.py
│       │   ├── cron.py
│       │   ├── hyros (via cron + hyros_service)
│       │   ├── ai_test.py / emails.py / olap.py / diagnostics.py
│       │   └── … (auth, subscribers, analytics, dashboard, settings)
│       ├── models/                  # org, subscriber, ad_campaign, campaign_utm, …
│       ├── services/
│       │   ├── ai_engine.py / classifier.py / response_generator.py
│       │   ├── follow_up_engine.py
│       │   ├── hyros_service.py
│       │   └── analytics_service.py
│       ├── integrations/
│       │   ├── messaging/manychat.py
│       │   └── meta/capi.py
│       ├── jobs/
│       │   ├── scheduler.py         # APScheduler (Hyros, follow-ups, OLAP)
│       │   ├── hyros_sync.py
│       │   ├── ad_spend_sync.py
│       │   ├── stale_conversations.py
│       │   └── daily_digest.py
│       └── utils/
│           └── dm_links.py          # attora_sub / attora_id on outbound URLs
│
├── scripts/
│   └── seed_warrior_babe_followups.py
├── docs/
│   ├── storefront-attribution.js
│   ├── hyros_attora_id_mapping.md
│   └── warrior_babe_ai_config_summary.txt
│
└── frontend/
    └── src/
        ├── pages/
        │   ├── CampaignsPage.tsx
        │   ├── PlaygroundPage.tsx
        │   └── … (dashboard, leads, analytics, settings)
        └── components/leads/LeadProfile.tsx  # full subscriber + attribution fields
```

## Development

### Backend only

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Requires Postgres and Redis running locally (or adjust `DATABASE_URL` / `REDIS_URL`).

### Frontend only

```bash
cd frontend
npm install
npm run dev
```

Vite dev server runs on `http://localhost:5173` with hot reload. API calls proxy to `http://localhost:8000`.

### Run migrations

```bash
# Inside the api container (or locally with DATABASE_URL set)
alembic upgrade head    # Apply all migrations
alembic downgrade -1    # Roll back one step
```

> **Before running in prod:** run `alembic upgrade head` to apply all pending migrations.

## Cron Jobs

Background work runs either via **HTTP cron endpoints** (`X-Cron-Secret`) or the **APScheduler** container (`hyros-scheduler` / `scheduler` profiles).

### Essential (most deployments)

```bash
# Stale conversations — daily
curl -X POST https://your-domain.com/api/cron/stale-conversations \
  -H "X-Cron-Secret: $CRON_SECRET"

# Daily analytics rollup — daily after midnight UTC
curl -X POST https://your-domain.com/api/cron/daily-digest \
  -H "X-Cron-Secret: $CRON_SECRET"

# Meta ad spend — daily or every few hours
curl -X POST https://your-domain.com/api/cron/ad-spend-sync \
  -H "X-Cron-Secret: $CRON_SECRET"

# Hyros purchases — every 3 hours (or use HYROS_SYNC_SCHEDULER_ENABLED)
curl -X POST https://your-domain.com/api/cron/hyros-sync \
  -H "X-Cron-Secret: $CRON_SECRET"

# Follow-up nudges — every 15 minutes (or use FOLLOW_UP_SCHEDULER_ENABLED)
curl -X POST https://your-domain.com/api/cron/follow-ups \
  -H "X-Cron-Secret: $CRON_SECRET"

# Dry run: eligibility only, no ManyChat sends
curl -X POST "https://your-domain.com/api/cron/follow-ups?dry_run=true" \
  -H "X-Cron-Secret: $CRON_SECRET"
```

### Self-hosted scheduler (recommended on AWS)

```bash
docker compose --profile hyros-scheduler up -d hyros-scheduler
```

Set in `.env` on the host:

```
HYROS_SYNC_SCHEDULER_ENABLED=true
FOLLOW_UP_SCHEDULER_ENABLED=true
CRON_SECRET=...
```

OLAP jobs (`export-ai-usage`, `archive-messages`, `check-olap-parity`) require `OLAP_SCHEDULER_ENABLED=true` and the `olap-selfhosted` profile — optional for MVP dashboard use.

## Key Metrics

The dashboard tracks these core KPIs:

- **CPQC** (Cost Per Qualified Conversation) — ad spend divided by conversations that reach `consideration` stage or beyond
- **CCR** (Conversation Conversion Rate) — percentage of conversations that result in a conversion
- **Funnel** — subscriber volume at each buyer stage (awareness → consideration → intent → purchase)
- **ROAS** (Return on Ad Spend) — revenue divided by ad spend (Hyros purchases + Meta spend when configured)
- **AI Performance** — fallback rate, average response time, token usage, estimated cost
- **Hyros match rate** — purchases attributed via `attora_id` / `attora_sub` / email (see `hyros_sync_logs`)

## License

Proprietary. All rights reserved.
