# Unit Economics

*Economic model for ReadPrism hosted service vs self-hosting. Aligned with
the plan structure in [HOSTING.md](HOSTING.md) and PRODUCT_PLAN §8. Prices are not
decided (#138); subscription prices are set at launch.*

## Plans and quotas

| Tier | Feeds | Creators | AI summaries / day | Newsletters / day | Manual builds / day | Price |
|---|---|---|---|---|---|---|
| **Self-host** | Unlimited | Unlimited | Unlimited (BYOK or local) | Unlimited | Unlimited | No license fee (MIT); the operator pays their own hosting |
| **Hosted Trial** (30 days) | 500 | 50 | 200 | 100 (50 MB) | 6 | Free, no card |
| **Hosted Reader** | 500 | 50 | 200 | 100 (50 MB) | 6 | Price set at launch |
| **Hosted Pro** | 2,000 | 200 | 1,000 | 300 (150 MB) | 12 | Price set at launch |
| **Free limits** (post-trial) | 30 | 5 | 20 | 20 (10 MB) | 3 | Free ($0) |

The full, configurable table is `DEFAULT_PLAN_QUOTAS` in `backend/app/config.py`
(see [Hosted service](HOSTING.md#plans-and-quotas)).

## Provider costs

- **LLM inference (Groq / provider):** primary model for synthesis and fast model
  for summaries (e.g. `openai/gpt-oss-120b` and `openai/gpt-oss-20b`). Typical
  rates: ~$0.075–0.15 / M input tokens, ~$0.30–0.60 / M output tokens.
- **Email delivery (Resend / SMTP):** free tier covers initial volume (~3,000/mo,
  100/day); paid tiers (e.g. $20/mo for 50k emails) behave as a **step cost**,
  not a linear per-user expense. Unverified accounts receive no digest emails.
- **Embeddings:** local sentence-transformers running on CPU workers, no external
  API cost.

## The load-bearing levers

### 1. Lazy summarization (on-demand, not upfront)

ReadPrism does **not** run LLM summaries on every ingested feed item. Feed items
receive fast extractive summaries at near-zero CPU cost during ingest. Full LLM
summaries are triggered **lazily** only when a user opens an item or requests a
summary. This caps token volume to what readers actually read rather than what
feeds publish.

### 2. Cross-user summary caching

Summaries for shared, publicly accessible feed items are cached globally
(`summarization_cached`). When multiple readers follow the same source or story,
the LLM cost is paid once:

- **Popular shared sources:** high cache-hit rate (>70%), amortizing inference
  cost across many subscribers.
- **Deep niche / personal feeds:** low cache-hit rate, where summaries are
  computed once per item read.
- **Private forwarded newsletters:** always private to the owning user; never
  shared, but volume is bounded by daily newsletter and summary quotas.

### 3. Readers' own LLM keys (BYOK)

Readers who add their own provider API key in Preferences run summaries directly
against their own provider account. For these readers, variable LLM inference
cost to the hosted instance is **$0**.

### 4. Merchant of Record (MoR) fees

Payments are processed through a Merchant of Record (Lemon Squeezy or Paddle) to
handle global sales tax, VAT, and GST compliance. MoR providers charge a transaction
fee (typically ~5% + $0.50 per transaction). Net revenue per subscriber equals the
subscription price (price set at launch) minus MoR fees.

## Break-even model

Per paying subscriber:

- **Net revenue** = price (set at launch) − merchant-of-record fees
- **Break-even** when net revenue > variable cost + allocated fixed cost

Where:
- **Variable cost per user:**
  - LLM tokens for opened items not already cached: capped by daily quotas (200/day on Reader, 1,000/day on Pro). For typical daily reading (5–15 articles read/day), this represents pennies per user per month.
  - Email step cost allocation.
- **Allocated fixed cost:** server hosting (e.g. Hetzner cloud node), domain, and
  off-box backup storage amortized across active users.
- **Safety valve:** post-trial non-paying users revert to Free limits (30 feeds,
  20 summaries/day, 3 digest builds/day), preventing unbounded variable cost from
  inactive or casual accounts while self-hosters incur no operator cost.
