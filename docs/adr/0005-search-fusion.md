# ADR 0005 — Search: Postgres FTS + pgvector fusion replaces the Meilisearch path

Date: 2026-10-02 · Status: accepted · Task: UX-11 · Decision: D-09

## Context

The spec asked for Meilisearch; D-09 revised it: keep the service count low,
use Postgres FTS + pgvector hybrid first, and only add Meilisearch if FTS
proves insufficient. Search was implemented Meilisearch-only
(`utils/search.py`, indexed on ingest); nothing degraded when Meilisearch
was absent — the endpoint silently returned zero hits.

## Decision

- `content_items.search_tsv` (migration 0018): weighted GENERATED tsvector
  (title A, headline+brief B), GIN-indexed.
- `GET /api/v1/search` runs two legs — `websearch_to_tsquery` + `ts_rank`,
  and a pgvector ANN query restricted to rows embedded by the active spec —
  fused with Reciprocal Rank Fusion (k=60; `services/search/hybrid.py`).
- Filters (source, origin, saved, since) apply inside BOTH legs, so fusion
  never leaks out-of-scope rows.
- Meilisearch stays dormant: the client code is kept, the endpoint no longer
  calls it. The compose service remains for operators who want it, but the
  app does not require it.

## Consequences

- One fewer hard runtime dependency; zero-hit mode is gone.
- `full_text` is excluded from the tsvector on purpose: it is large and is
  pruned by retention; summaries + titles stay. Recall over pruned bodies
  is a known, documented tradeoff.
- Latency budget (p95 < 300 ms at 100k items) relies on the GIN index and
  HNSW; a load benchmark is deferred to RL-06 (benchmarks page) — not yet
  measured at 100k rows.
- Meilisearch revisit criterion: if ranked-relevance complaints appear that
  RRF cannot fix (e.g. typo tolerance at scale), re-enable the dormant
  client behind a flag rather than re-implement.
