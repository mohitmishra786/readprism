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

Actually. `docker compose up`, one required env var (`GROQ_API_KEY`, free tier
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

Currently MIT (open and forkable — that's deliberate for a self-hostable tool;
the moat is accumulated behavioral data, which is per-instance and not portable).
An AGPL move is under consideration for the hosted offering. Contributions take a
DCO sign-off ([CONTRIBUTING.md](../CONTRIBUTING.md)).

### Pricing?

The full ranking engine is free. A planned hosted Pro (~$4.99/mo) gates
*quantity* (unlimited sources/creators, higher digest frequency, on-demand
synthesis) — not the intelligence. Priced on capability, not on being cheapest;
heavy users self-host. See [COMPETITORS.md](COMPETITORS.md).
