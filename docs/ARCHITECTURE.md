# Architecture (as the code is)

ReadPrism is a FastAPI process, three Celery workers plus beat, Postgres with
pgvector, Redis, an optional Browserless Chrome, Meilisearch, and a Next.js
app. Compose publishes the API on port 8000 and the UI on port 3001.

```
Next.js (App Router) -- /api/v1 --> FastAPI
                                   |-- async SQLAlchemy --> Postgres + pgvector
                                   |-- Redis (cache, rate limit, Celery)
                                   +-- Celery: scrape | embed | digest queues
```

Each worker uses `--pool=solo` so one asyncpg connection is not reused across
event loops. See `docs/adr/0001-celery-solo-pool.md`.

## Request path

`app/main.py` builds the app. Routers live under `app/api/` and are mounted at
`/api/v1`. Auth is a bearer JWT (`app/api/auth.py`). `GET /health` reports
database, Redis, and whether an LLM key is configured. It does not call the
provider.

## Ingestion

`app/workers/tasks/ingest_feeds.py` polls sources. RSS goes through
`rss_parser.fetch_feed`, which downloads with `safe_fetch` and parses the
bytes with feedparser. Each source stores `http_etag` and `http_last_modified`.
The next poll sends `If-None-Match` and `If-Modified-Since`. A 304 skips parsing.
Requests send `Accept-Encoding: gzip, deflate, br` and identify as
`ReadPrism/1.0 (+https://readprism.app/bot)`. Pages that are not feeds go through `scraper.scrape_page`:
robots.txt, then `safe_fetch`, then trafilatura, then Browserless if the bot
was not explicitly blocked. Newsletters arrive at `/api/v1/newsletter/inbound`
with a Mailgun signature (`app/api/newsletter.py`).

Creators are resolved in `app/services/creator/resolver.py`. Platform tiers
(`fully_tracked`, `best_effort`, `unsupported`) are the source of truth for
the UI badges. Twitter/X and LinkedIn are unsupported.

## Ranking

`compute_prs` (`app/services/ranking/scorer.py`) loads the user's weights and
the last 200 interactions, then runs eight signal modules in sequence on one
async session. The score is a weighted sum clamped to [0, 1]. Weights start
at the prior in `meta_weights.py` and move with gradient steps after enough
interactions. `reading_depth` and `explicit_feedback` are held out of that
gradient (`LEAKING_SIGNALS`) because they are derived from the same events the
learner is predicting. They are still features of the score.

The semantic signal compares the item embedding to the user's interest-graph
nodes (a mean-style vector plus bridge vectors for strong edges), not to a set
of cluster medoids. Embeddings are `all-MiniLM-L6-v2`, 384 dimensions,
`Vector(384)` in `content_items.embedding`. The input is title plus brief,
truncated to 2048 characters (`EmbeddingService.build_embedding_text`).

There is no `digest_impressions` table. A row in `user_content_interactions`
is created when an item is placed in a digest or when the client posts
telemetry.

## Digest

`build_digest` takes recent items from the user's sources, plus a serendipity
query for public items whose `source_id` is not one of those sources, inside
the same time window. On a one-user database that second set is empty unless
some other writer inserted public items. Sections (lead, creator, deep reads,
discovery) are assigned in `digest/sections.py` with a per-topic cap of 30%
and a serendipity share. Email rendering is `digest/delivery.py`.

## Summaries

`SummarizationService` calls `LLMClient` (`app/services/llm/client.py`). The
model id comes from settings. A failure, a missing key, or an open circuit
stores an extractive summary and sets `content_items.summary_source`.

## Search and the extension

`/api/v1/search` queries Meilisearch (`app/utils/search.py`). There is no
Postgres full-text index on the content body. The extension in `extension/`
is Manifest V3, Chrome-shaped (no `browser_specific_settings` for Firefox). It
POSTs the current page to `/api/v1/sources` or `/api/v1/creators` with a
bearer token stored in `chrome.storage.sync`.

## Tests

`backend/tests/` runs against Postgres. `tests/conftest.py` creates and drops
the schema per test. The default URL is
`postgresql+asyncpg://readprism:readprism@localhost:5432/readprism_test`.
Compose does not publish 5432, so the suite is run with
`docker run --network readprism_readprism_net` or `docker compose exec`.
