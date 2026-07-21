# ReadPrism

**The reading app that ranks by how you actually read.**

ReadPrism is a self-hostable reading tool that aggregates every source and creator you follow and orders your daily digest by personal relevance — a behavioral, explainable ranking engine that gets sharper the more you read.

What makes it different:

- **Behavioral, not keyword** — learns from real scroll depth and active reading time, not rules you maintain by hand (vs Feedly Leo).
- **Explainable** — every item shows why it ranked, and the interest graph names the topic connections (vs black-box feeds).
- **Honest and open** — the full ranking engine is free, closed platforms are marked unsupported rather than silently failing, and the code is open source and self-hostable.

The full product specification is in [`spec/PCIP_Proposal_V2.md`](spec/PCIP_Proposal_V2.md).

---

## Screenshots

> Visuals are captured into `docs/media/` — see [`docs/MEDIA.md`](docs/MEDIA.md)
> for the shot list and the `scripts/seed_demo.py` demo-data script. The hero
> shots are the ranked daily digest, the "why ranked" explanation, and the
> interest graph.

---

## What It Does

- **Unified ingestion** — RSS/Atom feeds, robust web scraping (trafilatura + Playwright fallback), newsletter forwarding, and creator tracking across Substack, YouTube, Medium, Reddit, podcasts (via iTunes lookup), and any blog with RSS autodiscovery.
- **Personalized Relevance Score (PRS)** — Eight signal dimensions combined with per-user learned weights rank every item before it reaches your digest.
- **Real reading telemetry** — An in-app reader captures genuine scroll depth, active reading time (paused on idle/hidden), and reached-end — feeding the behavioral signals (`reading_depth`, `temporal_context`, `suggestion`, `novelty`) with real data instead of a tab-switch heuristic.
- **Daily digest** — Sectioned into lead items, creator updates, deep reads, and discovery content, delivered by email and readable in-app.
- **Interest graph** — Your reading history is stored as a directed weighted graph of topics, not a flat keyword list, enabling transitive relevance and explainable rankings.
- **Cold start handling** — Onboarding extracts high-quality signal immediately; collaborative filtering warmup provides personalization before your own behavioral data accumulates.
- **Honest platform tiers** — Each tracked platform is shown as fully tracked / best-effort / unsupported, so you know what will and won't surface (Twitter/X and LinkedIn have no public feed and are clearly marked).

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (v2)
- A [Groq](https://console.groq.com/) API key (free tier is sufficient)
- SMTP credentials for email digest delivery (Zoho SMTP by default; any SMTP host works)
- 4 GB RAM minimum for the full stack (sentence-transformer model loads into memory)

---

## Setup

### 1. Clone and configure environment

```bash
git clone https://github.com/your-org/readprism.git
cd readprism
cp .env.example .env
```

Edit `.env` and fill in the required values:

```env
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
GROQ_API_KEY=<your Groq API key>
ZOHO_EMAIL=<your SMTP username>
ZOHO_PASSWORD=<your SMTP app password>
FROM_EMAIL=digest@yourdomain.com
FRONTEND_URL=http://localhost:3001
```

Only `GROQ_API_KEY` is strictly required to try the app locally — without email
credentials, digests are still readable in-app (email delivery is skipped). All
other values have working defaults for local development.

### 2. Start the stack

```bash
docker compose up --build
```

This starts seven services:

| Service | Port | Description |
|---|---|---|
| `db` | 5432 | PostgreSQL 16 with pgvector extension |
| `redis` | 6379 | Cache and Celery broker |
| `backend` | 8000 | FastAPI application server |
| `worker-scrape` / `worker-embed` / `worker-digest` | — | Celery workers, one `--pool=solo` process per queue (scrape / embed / digest) so a slow scrape can't starve digests |
| `beat` | — | Celery beat scheduler |
| `browserless` | 3000 | Headless Chrome pool for scraping |
| `frontend` | 3001 | Next.js web application |

### 3. Run migrations

```bash
docker compose exec backend alembic upgrade head
```

### 4. Open the app

Navigate to [http://localhost:3001](http://localhost:3001) and create an account. The onboarding wizard collects your interests, sample article ratings, and optionally imports an OPML file from an existing RSS reader.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Next.js Frontend (port 3001)                                   │
│  Digest reader · Source/creator management · Onboarding wizard  │
└─────────────────────┬───────────────────────────────────────────┘
                      │ REST /api/v1
┌─────────────────────▼───────────────────────────────────────────┐
│  FastAPI Backend (port 8000)                                    │
│  Auth · Sources · Creators · Content · Digest · Feedback        │
└──────┬──────────────┬──────────────────────────────────────────-┘
       │              │
       │              │ SQLAlchemy async
┌──────▼──────┐  ┌────▼──────────────────────────────────────────┐
│   Redis     │  │   PostgreSQL + pgvector                        │
│  Cache      │  │   Users · Sources · Creators · ContentItems    │
│  Celery     │  │   InterestNodes · InterestEdges · Digests      │
│  broker     │  │   UserContentInteractions                      │
└──────┬──────┘  └────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│  Celery Workers                                                 │
│  Ingest feeds (30 min) · Compute embeddings · Build digest      │
│  Deliver digest · Update interest graph · Apply decay (2 AM)    │
└─────────────────────────────────────────────────────────────────┘
```

### Intelligence pipeline (per ingested item)

1. Content extraction and cleaning
2. Semantic embedding via `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional, local — no API cost)
3. PRS computation against all users following that source (8 signals in parallel)
4. Deduplication by semantic similarity across items already in the user's queue
5. Summarization via Groq (`llama-3.3-70b-versatile`), cached in Redis

---

## Ranking Engine

Every piece of content receives a **Personalized Relevance Score (PRS)** computed as a weighted sum of eight signal dimensions. The weights are learned per-user via per-user gradient descent on prediction accuracy (the meta-learning layer in `services/ranking/meta_weights.py`).

```
PRS = w1·SemanticAlignment + w2·ReadingDepth + w3·SuggestionSignal
    + w4·ExplicitFeedback + w5·SourceTrust + w6·ContentQuality
    + w7·TemporalContext + w8·NoveltyAdjustment

where Σwᵢ = 1.0, all wᵢ learned per user
```

### Signal dimensions

| # | Signal | What it measures |
|---|---|---|
| 1 | **Semantic Alignment** | Cosine similarity between content embedding and user's interest vector |
| 2 | **Reading Depth** | Scroll depth, active reading time vs estimated reading time, reached-end, re-reads — captured by the in-app reader (`useReadingTelemetry`) |
| 3 | **Suggestion Signal** | Boosted weight when content is read from a source the user didn't follow |
| 4 | **Explicit Feedback** | Thumbs up/down, tagged reasons (too basic, too tangential, etc.), saves |
| 5 | **Source Trust** | Per-source (and per-creator-per-topic) trust weight learned from behavior |
| 6 | **Content Quality** | Article length, citation presence, vocabulary complexity, originality |
| 7 | **Temporal Context** | Three-scale model: long-term interests, medium-term focus (2–4 weeks), session saturation |
| 8 | **Novelty** | Configurable serendipity percentage (default 15%) for discovery outside established clusters |

New users start with equal weights, slightly biased toward semantic alignment and explicit feedback. The meta-learning layer adjusts weights as behavioral history accumulates.

### Interest graph

Your interest model is a directed weighted graph stored in PostgreSQL. Nodes are topic embeddings; edges represent co-occurrence in reading sessions. Node weights decay exponentially over time (core interests have longer half-lives). The graph enables transitive relevance — content at the intersection of two strongly connected topics scores highly even if you've never engaged with that exact subtopic before.

---

## Development Guide

### Running tests

```bash
docker compose exec backend pytest tests/ -v
```

Or locally with a running database:

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

### Local Celery (without Docker)

```bash
# Terminal 1 — worker
cd backend
celery -A app.workers.celery_app worker --loglevel=info

# Terminal 2 — beat scheduler
celery -A app.workers.celery_app beat --loglevel=info
```

### Frontend dev server

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

### Database migrations

```bash
# Inside the backend container or virtualenv
alembic upgrade head          # apply all migrations
alembic revision --autogenerate -m "description"  # generate new migration
alembic downgrade -1          # roll back one migration
```

### API documentation

FastAPI generates interactive docs at:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Key Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | JWT signing key — generate with `secrets.token_hex(32)` |
| `GROQ_API_KEY` | Yes | Primary LLM for summarization (Llama 3.3 70B) |
| `ZOHO_EMAIL` / `ZOHO_PASSWORD` | For email | SMTP credentials for digest delivery (email is skipped if unset) |
| `FROM_EMAIL` | For email | Sender address for digest emails |
| `FRONTEND_URL` | Yes | Used for CORS and email links |
| `PUBLIC_API_URL` | For email | Externally-reachable API URL for unsubscribe links |
| `OPENAI_API_KEY` | No | Fallback LLM (only used if `OPENAI_FALLBACK_ENABLED=true`) |
| `OPENAI_FALLBACK_ENABLED` | No | Default `false`. Set `true` to enable OpenAI fallback |
| `EMBEDDING_MODEL` | No | Default `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBEDDING_DEVICE` | No | Default `cpu`. Set `cuda` if GPU is available |

All variables are documented in [`.env.example`](.env.example).

---

## Scheduled Tasks

| Task | Schedule | Description |
|---|---|---|
| `ingest_all_feeds` | Every 30 minutes | Fetches and processes all active RSS/scraped sources |
| `ingest_creator_feeds` | Every 60 minutes | Fetches content from tracked creators across platforms |
| `schedule_daily_digests` | Daily at 05:00 UTC | Builds and queues digest delivery for all users |
| `apply_decay_all_users` | Daily at 02:00 UTC | Applies exponential decay to all interest graph node weights |
| `prune_old_full_text` | Daily at 03:30 UTC | Truncates stored article text to an excerpt after the retention window |

---

## Project Structure

```
readprism/
├── spec/PCIP_Proposal_V2.md          # Product specification (source of truth)
├── .env.example                       # All environment variables with descriptions
├── docker-compose.yml                 # Production-equivalent local stack
├── docker-compose.override.yml        # Local dev overrides
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt               # All Python deps pinned
│   ├── alembic.ini
│   ├── init.sql                       # pgvector extension initialization
│   ├── templates/digest_email.html    # Jinja2 email template
│   ├── migrations/
│   │   └── versions/                  # 0001 initial … 0006 content owner_user_id (per-user private content)
│   ├── tests/                         # pytest suite
│   └── app/
│       ├── main.py                    # FastAPI app factory + lifespan
│       ├── config.py                  # pydantic-settings BaseSettings
│       ├── database.py                # Async SQLAlchemy engine + session
│       ├── models/                    # SQLAlchemy ORM models (6 files)
│       ├── schemas/                   # Pydantic v2 request/response schemas (6 files)
│       ├── api/                       # FastAPI routers (8 endpoint files)
│       ├── utils/                     # embeddings, cache, email, logging
│       ├── workers/
│       │   ├── celery_app.py
│       │   ├── schedules.py
│       │   └── tasks/                 # 6 Celery task files
│       └── services/
│           ├── ingestion/             # rss_parser, scraper, newsletter, dispatcher
│           ├── ranking/               # engine, scorer, meta_weights + 8 signal modules
│           ├── interest_graph/        # graph, updater, decay
│           ├── digest/                # builder, sections, delivery
│           ├── summarization/         # groq_client, openai_client, summarizer
│           ├── creator/               # resolver, tracker
│           └── cold_start/            # onboarding, collaborative
└── frontend/
    ├── Dockerfile
    ├── package.json                   # All deps pinned (Next.js 16, React 19)
    ├── tsconfig.json
    ├── next.config.ts
    └── src/
        ├── app/                       # Next.js App Router pages (incl. /read/[id] in-app reader)
        ├── components/                # digest, onboarding, sources, creators, PlatformBadge
        └── lib/                       # types.ts, api.ts, auth.ts, useReadingTelemetry.ts
```

---

## Legal & Privacy

- [Privacy Policy](docs/PRIVACY.md) — what's collected, retention, and your export/erasure controls
- [Terms of Service](docs/TERMS.md)
- [Third-party services & compliance](docs/THIRD_PARTY_SERVICES.md)
- [Security policy](SECURITY.md) · [Contributing (+ CLA)](CONTRIBUTING.md)
- [Competitive landscape (2026)](docs/COMPETITORS.md) · [Unit economics](docs/UNIT_ECONOMICS.md)

These are baseline templates for the software; a hosted operator should have them
reviewed by counsel before collecting user data. The current license is
[MIT](LICENSE).

---

## Technology Stack

| Component | Technology |
|---|---|
| Backend API | Python 3.12 / FastAPI |
| Frontend | Next.js 16 (React 19, TypeScript) |
| Database | PostgreSQL 16 + pgvector |
| Cache & Queue | Redis 7 + Celery |
| Embeddings | sentence-transformers (local, no API cost) |
| Summarization LLM | Groq — Llama 3.3 70B (primary), Llama 3.1 8B (fast) |
| Email delivery | SMTP (Zoho by default) |
| Scraping | Playwright + Browserless/Chrome |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
