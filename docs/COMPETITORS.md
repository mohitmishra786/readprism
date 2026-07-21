# Competitive Landscape (refreshed, July 2026)

*The spec's original competitor table is stale in three ways: it omits NewsBlur
(the closest analog), omits the 2025–26 AI-native entrants, and understates
Inoreader (which now has an AI layer). This is the current, accurate version —
publish this, not the spec table, to avoid being corrected in public (audit
02-1). Prices verified July 2026.*

| Product | Price (Jul 2026) | AI / personalization | vs ReadPrism |
|---|---|---|---|
| **Feedly** | Free / Pro $6.99/mo / Pro+ ~$99/yr | Leo: keyword/topic rules, train-by-example (Pro+) | Feedly is keyword/rules; ReadPrism is behavioral + explainable |
| **Inoreader** | Free (150 feeds, ads) / Pro ~$7.50/mo annual | **Intelligence** summaries/smart-tags + **BYO-AI since Apr 2026** | Has AI now, but no *behavioral* ranking |
| **NewsBlur** | $36/yr Premium | **Trainable** per-user ranking (keyword/author/tag like-dislike, Bayes-style); self-hostable OSS | **Closest analog.** Semantic+telemetry vs keyword-Bayes; interest graph vs flat classifiers |
| **Readwise Reader** | $9.99/mo annual | Ghostreader summaries/prompts; no behavioral ranking | Read-later focus; no behavioral ranking |
| **Readless** | ~$4.90/mo | AI cross-source email digests; no ranking-by-behavior | Winning the category SEO war; not behavioral |
| **Meco** | Free / PRO ~$3.99/mo | AI summaries, newsletters only | Newsletters only |
| **Particle** | Consumer app | AI multi-source story summaries (general news) | General news, not your-sources |
| **Brief Digest / Daigest / TheReader.AI** | ~$2.99/mo Pro, free tiers | AI summaries/clustering/briefings | Cheaper; summaries not behavioral ranking |
| **auto-news (OSS)** | Free, self-hosted | LLM-filtered aggregation | The self-hosted OSS competitor class |

**Mailbrew** is free/dormant (maintenance mode since 2023) — drop it from any
active-competitor comparison.

## What is uniquely true

No one does **reading-telemetry-driven ranking + per-user learned weights +
self-hosting** together. Each piece individually now has a competitor; the
combination is still open. Market that true, provable version — not "no one does
this."

## Price positioning (audit 02-3)

ReadPrism Pro at **$4.99/mo** sits between the budget AI-digest entrants (Brief
Digest $2.99) and the incumbents (Inoreader ~$7.50, Feedly Pro+ ~$99/yr). Don't
race Brief Digest to the bottom — you can't win a price war while giving away LLM
inference. **Justify $4.99 on capability** (behavioral, explainable ranking + the
full engine free), not on being cheapest. Heavy/niche users self-host with their
own Groq key (see [UNIT_ECONOMICS.md](UNIT_ECONOMICS.md)).

*Quarterly refresh: re-run this table at launch and whenever Feedly/Inoreader
announce behavioral or BYO-model ranking. Last updated 2026-07-22.*
