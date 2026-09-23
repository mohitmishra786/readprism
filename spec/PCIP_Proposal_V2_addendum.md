# PCIP Proposal V2 — addendum

The proposal in `PCIP_Proposal_V2.md` is the intent. This file records where
the running code, or a binding decision in `docs/PROGRESS.md`, differs. Each
line cites a decision id.

| Topic | V2 said | What is true now | Decision |
|---|---|---|---|
| License | README once said MIT | `LICENSE` is AGPL-3.0-only. README matches the file. | D-12, OQ-01 (open, default is the LICENSE file) |
| Summarizer models | Groq Llama 3.3 70B and Llama 3.1 8B | `LLM_MODEL_PRIMARY` / `LLM_MODEL_FAST`. Defaults `openai/gpt-oss-120b` and `openai/gpt-oss-20b`. Retired ids are rewritten. | D-01 |
| Digest without an LLM | Summaries are part of the pipeline | Extractive summary is stored and the digest still builds. `summary_source` is `llm` or `extractive`. | D-02 |
| Embeddings | A single vector, model unspecified in places | `all-MiniLM-L6-v2`, 384-d, pgvector. The switch to `nomic-embed-text-v1.5` is not done; it waits on a golden retrieval check. | D-03 |
| Interest model | One interest representation, graph of topics | The graph is implemented (nodes, edges, decay). Scoring still uses node embeddings and bridge midpoints, not cluster medoids. | D-05 |
| Cold start | Collaborative filtering warmup | `cold_start/collaborative.py` returns no items when fewer than `COLLABORATIVE_WARMUP_MIN_USERS` (default 1000) distinct users have interactions. A single-user instance does not error. | D-06 |
| Suggestion candidates | Content the user did not follow | Serendipity selects public `content_items` whose source is not in the user's source list, inside the digest window. Nothing ingests a discovery corpus, so a one-user database has no such rows. | D-06, roadmap IQ-06 |
| Search | Meilisearch | Meilisearch is in compose and `app/utils/search.py`. Postgres FTS is not built. Revisit is UX-11. | D-09 |
| Hosted product | Tiers, team digests, pricing pages exist in the tree | Team tables and a pricing discussion exist in code and docs. They are not the product plan. EC-09 and RL-09 are dropped until there is pull. | D-10 |
| Platform connectors | Broad creator coverage | Native recipes for several platforms, honest unsupported tier for X and LinkedIn. RSSHub bridge is not implemented. | D-11 |
| Paywalls and robots | Not always explicit | Scrape mode checks robots.txt and fails closed when robots cannot be fetched. Known paywall bypass is not implemented. | D-08 |
| Telemetry export | Not specified as forbidden | No product analytics SDK. Sentry is off without `SENTRY_DSN`. | D-07 |
| Competitor table (Feb 2026) | Inoreader has no AI layer; prices as of the proposal | The table in `docs/ROADMAP.md` §4 is the September 2026 pass. Prices marked there are unverified vendor pages. Do not republish them without checking. | Roadmap F9 |

Ranking math in the proposal (eight signals, learned weights, explainable sum)
is still the shape of `compute_prs`. The feature definitions in the roadmap
(pre-consumption predictions, impression log, MMR, label table) are not what
the signal modules compute today. See the Spec Coverage Matrix in
`docs/PROGRESS.md`.
