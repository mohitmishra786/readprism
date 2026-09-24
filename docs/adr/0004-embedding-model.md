# ADR 0004 — Keep MiniLM until Nomic wins the retrieval check

- **Status:** Accepted
- **Date:** 2026-09-25
- **Context tags:** embeddings, iq-02, d-03

## Context

`all-MiniLM-L6-v2` truncates long articles. `nomic-embed-text-v1.5` has a longer context and needs `search_document:` / `search_query:` prefixes, plus a 768-d column. D-03 says the default changes only after a golden retrieval check.

## Options

1. Switch to Nomic now and backfill every row.
2. Keep MiniLM, ship the check, and cut over only when Nomic's MRR is higher.

## Decision

Option 2. The active model is `all-MiniLM-L6-v2` (384-d). `EMBEDDING_CUTOVER_ENABLED` defaults to false, which is also the lite profile. The registry knows Nomic's name, dimension, and prefixes, and rows store `embedding_model`, `embedding_dim`, and `embedding_version` so two models can coexist. Queries that compare vectors must filter to the active model.

The check in `app/services/embeddings/retrieval.py` scores 200 fixture pairs. A truncated encoder against a full-text encoder shows whether seeing the later topic token improves MRR. A two-way tie uses expected reciprocal rank 0.75. Nomic's weights were not downloaded. `content_items.embedding` is `Vector(384)`, so `resolve_stored_model` keeps MiniLM even if `EMBEDDING_MODEL` or the cutover flag names Nomic. A 768-d column has to exist before that model can be selected.

Fixture result (not Nomic weights): the full-text encoder beats the 8-token prefix encoder on those 200 pairs. That justifies encoding body windows separately. It does not justify a dimension change. `stamp_stored_embeddings` writes model identity onto existing vectors in committed id-ordered batches.

The HNSW cosine index on `content_items.embedding` already exists from migration 0001. Rollback of 0013 drops the identity columns and the new tables and leaves the vectors and that index in place.

RAM: MiniLM stays the lite and default profile. Nomic is not loaded, so this change does not add a second model to the process.

## Consequences

Backfill of model metadata is resumable (`backfill_batch`) and does not rewrite vectors. A 50k-row stamp was not executed in CI; the cursor test covers a 1,000-row batch. Operators can run the same function over the live table before any cutover.
