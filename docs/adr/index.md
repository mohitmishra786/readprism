# Decision records

<p class="lead">Why ReadPrism is built the way it is. Each record states the
problem, the options considered and the decision, so a change of course can
start from the same facts.</p>

| Record | Decision | Status |
|---|---|---|
| [0001: Celery solo pools](0001-celery-solo-pool.md) | One process per worker, scale by adding workers | Accepted |
| [0002: Provider-agnostic LLM client](0002-provider-agnostic-llm.md) | Any OpenAI-compatible endpoint; model ids are configuration | Accepted |
| [0003: Safe outbound fetching](0003-safe-fetch.md) | Every user URL goes through one SSRF-checked fetcher | Accepted |
| [0004: Embedding model](0004-embedding-model.md) | Keep `all-MiniLM-L6-v2` (384-d) until a measured cut-over | Accepted |
| [0005: Search on Postgres](0005-search-fusion.md) | Full-text search and pgvector, fused; no separate search service | Accepted |
| [0007: Sidecar import](0007-reader-api-compat.md) | Import from Miniflux or FreshRSS through their reader APIs | Proposed |

New records start from the [template](0000-template.md).
