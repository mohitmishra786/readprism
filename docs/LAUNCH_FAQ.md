# Launch FAQ (prewritten answers)

*The same five questions come up on Show HN / r/rss / r/selfhosted. Prewritten,
honest answers so you can respond fast and consistently (audit 15-3). Keep the
humble, technical register HN rewards.*

### How is this different from NewsBlur? (the first question r/rss will ask)

NewsBlur is the closest analog and genuinely good. The difference is *what the
training is based on*: NewsBlur's Intelligence trains on like/dislike of
keywords, authors, and tags (transparent, Bayes-style); ReadPrism learns from how
you actually read — semantic embeddings plus real reading telemetry (scroll
depth, active time) — and models interests as a decaying graph with transitive
relevance, not flat per-feed classifiers. Less manual training, but it needs more
reading history. Full comparison: `/vs/newsblur`.

### Isn't the cold start bad? Day 1 it can't know me.

Correct, and it's the hardest problem in any personalization product — we're
up front about it. Day 1 is: onboarding topics → embedding similarity against
curated starter sources. It gets noticeably sharper over the first 1–2 weeks as
behavioral signal accumulates. There's an honest "gathering your first reads"
state instead of a fake-confident empty digest, and you can validate the learning
yourself with `scripts/ranking_eval.py` (read-prediction AUC per cohort).

### Is it actually self-hostable, or is that aspirational?

Actually. `docker compose up`, one required env var (`LLM_API_KEY`, free tier
fine), and you're running the full engine on your own Postgres/Redis. Bring your
own LLM key so heavy/niche use is on your bill, not a hosted service. See the
README quickstart.

### What's the privacy story? It tracks my reading.

Yes — behavioral telemetry is how it ranks. It's all on your instance
(self-hosted) or the hosted operator's. There's a full data export
(`GET /account/export`) and one-click account deletion, a documented retention
policy that prunes stored full-text to excerpts after 90 days, and no ad/tracking
resale. See [PRIVACY.md](PRIVACY.md).

### What's the license / can a competitor just fork it?

MIT (relicensed from AGPL-3.0 on 2026-10-02, decision D-13). Use, modify,
self-host, and fork freely — keep the license notice. The moat is accumulated
behavioral data (per-instance, not portable), not license restrictions.
Contributions take a DCO sign-off
([CONTRIBUTING.md](https://github.com/mohitmishra786/readprism/blob/main/CONTRIBUTING.md)).

### Pricing?

The self-hosted version is free and open-source (MIT) with no plan limits. The
hosted service gives every reader a 30-day trial with Reader limits (500 feeds,
200 AI summaries/day), followed by paid Reader and Pro plans (price set at
launch) or Free limits after the trial (30 feeds, 20 AI summaries/day). Paid plans
gate quantity (more feeds, newsletters, and daily AI summaries) — not the ranking
intelligence. Readers can also bring their own LLM key to run summaries on their
own provider account outside the quota. See [HOSTING.md](HOSTING.md).
