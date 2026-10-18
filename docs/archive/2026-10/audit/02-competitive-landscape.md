# 02 — Competitive Landscape Update (July 2026)

*Evidence types: **spec says** / **code shows** / **market shows** (all pricing verified via web search July 2026 — links inline).*

## Status Snapshot

- The spec's competitor table (Feb 2026) is already stale in three ways: it omits NewsBlur (the closest behavioral-ranking analog), omits the 2025–26 AI-native entrants, and understates Inoreader (which now *does* have an AI layer — the spec says "no AI layer whatsoever," which was outdated even when written).
- ReadPrism's planned $4.99 Pro price undercuts the incumbents but sits *above* the new budget AI-digest entrants (Brief Digest $2.99, Meco $2.92/mo annual).
- Nobody in the field does reading-telemetry-driven ranking + per-user learned weights + self-hosting together. That combination is still open. Each piece individually now has a competitor.
- The graveyard matters: Artifact (2024) and Apricot (Dec 2025) both died doing AI-personalized news. Distribution, not ranking quality, killed them.

## Refreshed competitor table

| Product | Current price (Jul 2026) | AI/personalization | Change vs spec's claims |
|---|---|---|---|
| **Feedly** | Free / Pro $6.99/mo / Pro+ $12.99/mo ($99/yr annual ≈ $8.25/mo) ([socialrails](https://socialrails.com/blog/feedly-pricing), [feedly.com](https://feedly.com/market-intelligence/pricing)) | Leo: keyword/topic rules, Like-Board train-by-example, summaries — Pro+ only | Spec's "$12.99/mo" is the monthly rate; annual is ~$8.25 — spec's price-anchoring vs Feedly should quote $99/yr |
| **Inoreader** | Free (150 feeds, ads) / Pro $7.50/mo annual, $9.99 monthly ([inoreader.com/pricing](https://www.inoreader.com/pricing)) | **Intelligence**: summaries, reports, smart tags, 1M tokens/mo; **BYOAI since Apr 2026** (own OpenAI/Anthropic/Mistral key) ([Inoreader blog](https://www.inoreader.com/blog/2026/04/choose-your-ai-platform-for-intelligence-features.html)) | **Spec is wrong**: "no AI layer whatsoever" no longer true. Still no *behavioral* ranking though |
| **Readwise Reader** | $9.99/mo annual, $12.99 monthly; no free tier ([readwise.io](https://readwise.io/pricing/reader)) | Ghostreader summaries/GPT prompts; no behavioral ranking | Matches spec's $9.99 claim |
| **Readless** | ~$4.90/mo Pro ([readless.app](https://www.readless.app)) | AI cross-source email digests, RSS + newsletters; no ranking-by-behavior. Aggressive SEO content machine (dozens of comparison pages dominate search results) | Spec's "no ranking layer" still true; but Readless is winning the *SEO war* for this category — see artifact 11 |
| **Meco** | Free / PRO $3.99/mo, $34.99/yr ([meco.app](https://meco.app/), [docs](https://docs.meco.app/docs/meco-pro/overview)) | AI summaries, personalized podcasts; newsletters only | Matches spec |
| **Mailbrew** | **Free** since 2023 ownership change; maintenance mode ([mailbrew.com](https://mailbrew.com/)) | None | Spec treats it as an active paid competitor; it's effectively a zombie product |
| **NewsBlur** | $36/yr Premium; $99/yr Premium Archive w/ Ask AI ([Readless comparison](https://www.readless.app/blog/feedly-vs-inoreader-vs-newsblur-2026)) | **Trainable per-user ranking** (like/dislike phrases, authors, tags — Bayes-style, transparent) + self-hostable OSS | **Missing from spec entirely.** Closest analog to ReadPrism's pitch; LAUNCH.md acknowledges it, spec doesn't |
| **Particle** | Consumer app | AI multi-source story summaries, "best AI news aggregator 2026" per roundups ([Readless roundup](https://www.readless.app/blog/best-ai-news-aggregators-2026)) | New entrant, not in spec. General news, not your-sources |
| **Brief Digest / Daigest / LetMeKnow / TheReader.AI** | $2.99/mo Pro (Brief Digest); free tiers common | AI summaries, clustering, scheduled briefings (RSS+YouTube+Reddit+X for Daigest) | New 2025–26 entrants, none in spec; all cheaper than ReadPrism Pro |
| **auto-news (OSS)** | Free, self-hosted ([github](https://github.com/finaldie/auto-news)) | LLM-filtered multi-source aggregation | The self-hosted OSS competitor class the spec ignores |

## Where the spec's claims are now outdated

1. **"Inoreader has no AI layer whatsoever"** — false as of 2026 (Intelligence + BYOAI). The capability-table row "Inoreader: No" for semantic features needs revision.
2. **Mailbrew as a paid competitor** — it's free/dormant; drop it, replace with NewsBlur + Readless + Particle.
3. **Feedly price anchoring** — quote $99/yr Pro+ annual, not only $12.99/mo, or the comparison reads as cherry-picked.
4. **"Available on free tier: PCIP yes, others no"** — Inoreader free tier now includes 150 feeds + newsletter feeds (no AI); Brief Digest includes AI on free. The row survives only if narrowed to "full behavioral ranking engine free."
5. **Social-platform ingestion assumptions** — see artifact 08/07: X API free tier is dead (pay-per-use, Feb 2026), Reddit is $0.24/1k calls with approval gates. The spec's "graceful fallback" framing is right; any residual implication that X/Reddit tracking is feasible is not.

## Checklist

- [ ] P0 | Rewrite the spec's competitor table with the data above (esp. Inoreader AI, NewsBlur row) | Launching with a visibly outdated comparison invites public correction | This artifact's table | S | founder
- [ ] P1 | Build /vs/feedly, /vs/inoreader, /vs/newsblur comparison pages before launch | Readless is capturing the entire category's comparison-search traffic | Readless SEO footprint in every search above | M | founder
- [ ] P1 | Position price between Brief Digest ($2.99) and Inoreader ($7.50): justify $4.99 with the ranking engine explicitly | Mid-price with undifferentiated messaging loses both directions | pricing table, spec §Pricing | S | founder
- [ ] P1 | Add a NewsBlur-differentiation FAQ (semantic+telemetry vs keyword-Bayes; graph vs flat) | First question any r/rss power user will ask; LAUNCH.md already drafts it | docs/LAUNCH.md | S | founder
- [ ] P2 | Track Feedly Leo releases quarterly for behavioral-signal features | Spec names this as the incumbent-response risk | spec §Risks | S | none-needed-yet
- [ ] P2 | Watch Particle/TheReader.AI for a move from general news to user-chosen sources | That move would collide directly with the wedge | market search | S | none-needed-yet

## Top 5 if you only do 5 things

1. Fix the Inoreader and NewsBlur rows in every public comparison before anyone else does it for you.
2. Ship 3 comparison landing pages (Feedly, Inoreader, NewsBlur) — this is also the SEO play.
3. Re-anchor pricing copy against $99/yr Feedly Pro+ annual and $2.99 Brief Digest.
4. Steal the lesson from Artifact/Apricot: personalization quality did not save them — plan distribution first.
5. Keep a quarterly competitor-refresh note in the repo (this file is the first entry).

**Revisit trigger:** re-run at launch, and any time Feedly/Inoreader announce behavioral or BYO-model ranking features.
