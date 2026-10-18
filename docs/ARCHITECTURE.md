# System Architecture

ReadPrism is a personal reading digest service that aggregates RSS feeds, newsletters, and creator profiles, summarizes articles, and ranks a daily digest using a personal behavioral ranker.

It is designed to run in two deployment modes:
- **`DEPLOYMENT_MODE=selfhost`** (default): fully featured personal instance, closed registration by default, unlimited sources, zero billing or usage budgets.
- **`DEPLOYMENT_MODE=hosted`**: multi-tenant production SaaS with mandatory email verification, rate limits, source/fetch abuse controls, and subscription billing.

---

## 1. High-Level Component Topology

```mermaid
flowchart TD
    subgraph Clients["Clients"]
        Web["Next.js 16 Web App\n(Port 3000 / 3001)"]
        Ext["Cross-Browser MV3 Extension\n(Chrome / Firefox)"]
    end

    subgraph Edge["Ingress & Egress"]
        Egress["Browserless Chrome\n(Isolated Egress Proxy)"]
    end

    subgraph Backend["FastAPI Application (Port 8000)"]
        API["FastAPI App\n(api/v1)"]
        Migrate["Auto-Migrate on Boot\n(app/migrate.py)"]
        Cookies["Cookie Sessions & CSRF\n(session_cookies.py)"]
        Ranker["Vectorized Ranker\n(ranking/ranker.py)"]
        Learner["Pairwise Learner\n(ranking/learner.py)"]
        LazyLLM["Lazy LLM Summarizer\n(summarization/lazy.py)"]
    end

    subgraph Workers["Celery Workers (Solo Pools)"]
        ScrapeWorker["Worker: scrape\n(Feeds & Scrapes)"]
        EmbedWorker["Worker: embed\n(Sentence Transformers)"]
        DigestWorker["Worker: digest\n(Build & Delivery)"]
        BeatWorker["Celery Beat\n(Periodic Schedulers)"]
    end

    subgraph Storage["Data Stores"]
        PG[("PostgreSQL 16+ & pgvector\n(Shared Feeds, Content, Vectors)")]
        Redis[("Redis 7+\n(Broker, Result Store, Cache, Rate Limits)")]
    end

    Web -->|HTTP with Cookies & CSRF| API
    Ext -->|Bearer / API Token rp_...| API
    API --> PG
    API --> Redis
    API -.-> LazyLLM
    ScrapeWorker --> PG
    ScrapeWorker --> Redis
    ScrapeWorker -->|safe_fetch + IP Pinning| Egress
    EmbedWorker --> PG
    EmbedWorker --> Redis
    DigestWorker --> PG
    DigestWorker --> Redis
    BeatWorker --> Redis
    Migrate -->|Postgres Advisory Lock| PG
```

### Worker Concurrency
Celery workers run with `--pool=solo` (`docs/adr/0001-celery-solo-pool.md`) so that `asyncpg` connection pools are never shared across disparate asyncio event loops in child processes. Tasks are strictly routed to named queues (`scrape`, `embed`, `digest`).

---

## 2. Ingestion & Shared Feeds

### Shared Feeds Pipeline
Subscriptions are separated into per-user subscriptions (`sources` table) and instance-wide polling rows (`feeds` table):
- **Shared Identity**: `Feed.key = coalesce(feed_url, url)`. $N$ users subscribing to the same RSS feed trigger only a single network fetch per poll cycle.
- **State Mirroring**: `app/services/ingestion/feeds.py` (`mirror()`) copies HTTP etags, Last-Modified headers, poll intervals, error states, and dead notices onto every subscriber's `Source` row after each poll.
- **Adaptive Scheduling**: `app/services/ingestion/schedule.py` dynamically adjusts poll intervals between 15 minutes and 24 hours based on recent publication cadence, backing off exponentially on HTTP errors and honoring `Retry-After`.
- **SSRF Defense with IP Pinning**: `app/utils/ssrf.py` validates public IPs before network requests. `safe_fetch` connects directly to the validated IP literal while preserving the original `Host` and TLS SNI headers, eliminating DNS rebinding vulnerabilities. Local homelab exemptions are opt-in via `SIDECAR_ALLOW_PRIVATE_HTTP`.
- **Content Deduplication**: Ingested items are deduplicated across three layers: canonical URL normalization, GUID matches, and SimHash Hamming distance for near-duplicate article text.
- **Platform Connectors**:
  - Fully tracked: Substack, Medium, YouTube, Bluesky, Mastodon, GitHub.
  - Best-effort: Blogs and podcasts (via iTunes search autodiscovery).
  - Unsupported: Twitter/X, LinkedIn, and Reddit (RSS retired on 2026-11-13). Unsupported platforms surface clear UI warnings and never error-loop.

---

## 3. The Personal Ranking Engine

ReadPrism replaced per-item signal modules with a unified, vectorized ranking pipeline (`app/services/ranking/ranker.py`):

```mermaid
sequenceDiagram
    participant S as Scheduler / API
    participant R as Ranker (ranker.py)
    participant PG as PostgreSQL / pgvector
    participant L as Learner (learner.py)

    S->>R: rank(user, candidates, session)
    R->>PG: Batch load user weights, interest graph, reading history
    R->>R: Vectorized feature matrix computation (8 signals via NumPy)
    R->>R: Weighted dot product -> Personalized PRS score [0, 1]
    R->>R: Apply MMR diversity (penalty on topic clustering)
    R->>R: Team-draft interleaving (PRS vs Newest-First)
    R-->>S: Ranked candidate list + feature decomposition
    Note over S,L: User reads & rates items in digest
    S->>L: train_user_weights_debounced(user_id)
    L->>L: Pairwise within-digest loss optimization
    L->>PG: Save updated UserMetaWeights revision
```

### Feature Decomposition
Every candidate is evaluated on 8 orthogonal features normalized to $[0, 1]$ before consumption:
1. `semantic`: Cosine similarity against interest-graph nodes and bridge midpoints.
2. `reading_depth`: Similarity-weighted historical completion of opened articles.
3. `suggestion`: Acceptance/completion rate for discovery items.
4. `explicit_feedback`: Closeness to thumbs-up articles minus thumbs-down penalties.
5. `source_trust`: Beta posterior of reading outcomes on this specific feed with the user's prior.
6. `content_quality`: Text length, citation structure, and depth heuristics.
7. `temporal_context`: Age decay with same-event saturation penalties.
8. `novelty`: Semantic distance from the last 30 days of user reading history.

When evidence is missing, features default to a neutral `0.5`, contributing zero gradient to pairwise learning.

### Diversity & Experimentation
- **MMR (Maximal Marginal Relevance)**: Penalizes semantic redundancy among top candidates to prevent single-topic monopolization.
- **Team-Draft Interleaving**: Alternates selections between the personalized ranker and a newest-first baseline to continuously measure ranking win-rate in production without degrading reading flow.
- **Pairwise Learning**: Weights are trained on within-digest preference pairs (opened vs skipped items within the same digest) rather than noisy absolute clicks, debounced per user.

---

## 4. Digest Building & Summarization

### Assembly & Sections
`app/services/digest/builder.py` personalizes sections for each reader:
- **Lead Section**: Top-scoring articles.
- **From Your Creators**: Grouped by creator (max 2 items per creator).
- **Deep Reads**: High-scoring long-form content ($\ge 8$ min reading time).
- **Discovery**: Serendipity picks from the Discovery Pool (`app/services/discovery/pool.py`), surfacing outbound links and starter-pack items matching interest clusters.
- **More From Your Feeds**: Fills remaining capacity to target length.

### Dynamic Digest Length & Schedule
- **Adaptive Length**: `digest_max_items` dynamically tracks $1.25 \times \text{EMA}(\text{opened items})$, clamped to $[5, 30]$ unless explicitly locked by user preference.
- **Zoneinfo Delivery**: Digests fire within a $\pm 15$-minute window around the user's preferred local time slot, with frequency deduplication windows (12h daily, 6h twice-daily, 84h weekly) preventing duplicate builds.

### Lazy LLM Summarization
Rather than invoking LLMs on all ingested articles, summarization is lazy (`app/services/summarization/lazy.py`):
1. Ingestion extracts a clean fallback text brief.
2. An LLM summary is only generated when an item is placed in a delivered digest or explicitly opened in the app.

---

## 5. Security, Sessions, and Operations

### Cookie Authentication & CSRF
- Browser credentials are stored in `httpOnly`, `SameSite=Lax` secure cookies (`readprism_access`, `readprism_refresh`).
- Mutating endpoints verify double-submit CSRF tokens via `x-csrf-token` header.
- Scoped API tokens (`rp_<hash>`) provide secure programmatic access for CLI tools and the browser extension.

### Database Migrations
Migrations execute via `app/migrate.py` on startup under Postgres advisory lock `7302410126`. When multiple API or worker containers start simultaneously, exactly one runs migrations while others wait.

### Hosted Multi-Tenancy & Abuse Controls
Under `DEPLOYMENT_MODE=hosted`:
- User registration enforces email confirmation (`app/services/email_verification.py`).
- Feed fetching enforces hourly host poll limits and account-level fetch budgets (`app/services/abuse.py`).
- Source limits and subscriber tiers are gated by LemonSqueezy/Stripe webhooks (`app/services/billing.py`).
- Full-text retention pruning runs on beat schedule to manage storage growth.

### Queue Metrics & Observability
Celery task wait times, run durations, and queue latencies are instrumented in `app/workers/queue_metrics.py` and exposed at `GET /api/v1/metrics/queues` guarded by `METRICS_TOKEN`.
