# ReadPrism

**Personalized Content Intelligence Platform**

ReadPrism is a self-hostable reading tool that aggregates content from every source and creator you follow, ranks it by personal relevance using a continuously learning model, and delivers a daily digest containing exactly what you need to read — in the right order, for you specifically.

The full product specification is in [`spec/PCIP_Proposal_V2.md`](spec/PCIP_Proposal_V2.md).

---

## What It Does

- **Unified ingestion** — RSS/Atom feeds, web scraping via headless browser, newsletter forwarding, and creator tracking across Substack, YouTube, personal blogs, Medium, and more.
- **Personalized Relevance Score (PRS)** — Eight signal dimensions combined with per-user learned weights rank every item before it reaches your digest.
- **Daily digest** — Sectioned into lead items, creator updates, deep reads, and discovery content, delivered by email and readable in-app.
- **Interest graph** — Your reading history is stored as a directed weighted graph of topics, not a flat keyword list, enabling transitive relevance and explainable rankings.
- **Cold start handling** — Onboarding extracts high-quality signal immediately; collaborative filtering warmup provides personalization before your own behavioral data accumulates.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (v2)
- A [Groq](https://console.groq.com/) API key (free tier is sufficient)
- A [Resend](https://resend.com/) API key for email digest delivery
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
RESEND_API_KEY=<your Resend API key>
FROM_EMAIL=digest@yourdomain.com
FRONTEND_URL=http://localhost:3001
```

All other values have working defaults for local development.

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
| `worker` | — | Celery task worker (4 concurrency) |
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

Every piece of content receives a **Personalized Relevance Score (PRS)** computed as a weighted sum of eight signal dimensions. The weights are learned per-user via gradient descent on prediction accuracy.

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
| 2 | **Reading Depth** | Scroll completion, time on page vs estimated reading time, re-reads |
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
| `RESEND_API_KEY` | Yes | Email digest delivery |
| `FROM_EMAIL` | Yes | Sender address for digest emails |
| `FRONTEND_URL` | Yes | Used for CORS and email links |
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
│   │   └── versions/0001_initial_schema.py
│   ├── tests/                         # pytest suite (9 test files)
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
    ├── package.json                   # All deps pinned (Next.js 14, React 18)
    ├── tsconfig.json
    ├── next.config.ts
    └── src/
        ├── app/                       # Next.js App Router pages
        ├── components/                # React components (digest, onboarding, sources, creators)
        └── lib/                       # types.ts, api.ts, auth.ts
```

---

## Technology Stack

| Component | Technology |
|---|---|
| Backend API | Python 3.11 / FastAPI |
| Frontend | Next.js 14 (React 18, TypeScript) |
| Database | PostgreSQL 16 + pgvector |
| Cache & Queue | Redis 7 + Celery |
| Embeddings | sentence-transformers (local, no API cost) |
| Summarization LLM | Groq — Llama 3.3 70B (primary), Llama 3.1 8B (fast) |
| Email delivery | Resend |
| Scraping | Playwright + Browserless/Chrome |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
