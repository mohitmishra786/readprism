# Weirling: Launch materials

Ready-to-use copy for launch posts. Keep it honest and specific; the HN/r/rss
audience punishes hype and rewards technical substance.

---

## Hacker News: title + body

**Title:** Show HN: Weirling: an RSS/creator aggregator that ranks by personal relevance

**Body:**

Hi HN. I built Weirling because following 80 sources left me triaging 200 items
a day, and every reader I tried was either a chronological firehose (Inoreader)
or a keyword filter I had to babysit (Feedly Leo).

The core idea: relevance is a relationship between content, a specific person,
and time, not a property of content alone. So Weirling computes a
Personalized Relevance Score per item, per user, from eight signals:

- Semantic alignment (sentence-transformer embeddings, not keywords)
- Reading depth (real scroll-depth + active-time telemetry, not clicks)
- Source/creator trust (learned per-user, even per creator-topic intersection)
- Temporal context (long-term interests + medium-term focus + session saturation)
- Suggestion signal (the purest signal: what you read from sources you didn't follow)
- Explicit feedback, content quality, and a configurable serendipity layer

The weights are learned per-user via gradient descent on prediction accuracy,
so the engine gets sharper the more you use it, and that learned model is the
moat: an 18-month-old interest graph isn't portable to a competitor.

It's fully open-source and self-hostable (Docker Compose, Postgres+pgvector, Redis,
Celery, FastAPI, Next.js). Hosted accounts get a 30-day trial of Pro, then Reader
($6/month or $54/year) or Pro ($12/month or $108/year); there is no free hosted plan.
Closed platforms (X, LinkedIn, Reddit) are honestly marked "unsupported" rather than
silently failing.

I'm most curious about feedback on the cold-start problem, the hardest part of
any personalization product. I seed curated starter sources + use collaborative
warmup, but day-1 quality is the existential risk and I'd value thoughts.

Repo: https://github.com/mohitmishra786/weirling

---

## r/rss and r/selfhosted: shorter version

**Title:** Weirling: a self-hostable RSS reader with behavioral ranking (not keyword filters)

**Body:**

Tired of chronological feeds and Feedly's keyword-AI, I built a reader that
ranks by *how you actually read* (scroll depth, active time, what you re-read,
and what you skip). Eight ranking signals with per-user learned weights, stored
as a directed interest graph (so it knows that compiler-optimization and
language-design are adjacent in your reading).

- Self-hostable: Docker Compose, Postgres+pgvector, Redis, Celery
- Tracks RSS, scraping (trafilatura + Playwright fallback), newsletters, creators
- Substack, YouTube, Medium, Bluesky, Mastodon, GitHub and podcasts supported;
  X, LinkedIn and Reddit honestly marked unsupported
- Self-hosted has no plan limits; hosted accounts get a 30-day Pro trial, then Reader ($6/mo) or Pro ($12/mo); no free hosted plan
- Open source (MIT)

The interesting trade-off: the ranking needs behavioral signal, which means it's
weak for light users and strongest for daily readers. Curious how the r/rss
power-user crowd finds it vs NewsBlur's Intelligence Trainer (which I'd consider
the closest analog, though it's keyword/Bayes rather than behavioral+semantic).

---

## Positioning one-liner (for anywhere)

> Weirling aggregates every source and creator you follow and ranks it by
> personal relevance: a learning engine that gets sharper the more you read.

## Three differentiation bullets (for comments/DMs)

1. **Behavioral, not keyword.** Learns from scroll depth + active time, not
   keyword rules you maintain by hand.
2. **Explainable.** "Why this?" shows the signals and their contribution, and
   the interest graph can name the topic connections that drove a ranking.
3. **Honest about limits.** Closed platforms are marked unsupported, not
   silently broken; the full ranking engine is free, not paywalled.
