# ReadPrism — Analysis, Competitive Research & Product Roadmap

**Prepared:** 24 Sep 2026 · **Repo:** github.com/mohitmishra786/readprism · **Spec:** `spec/PCIP_Proposal_V2.md`
**Companion files:** `PROGRESS.md` (task backlog + tracker) · `GLM_MASTER_PROMPT.md` (execution prompt)

---

## 0. Read this first — what I could and could not see

Be careful how much weight you put on the "where we stand" section. Here is exactly what the analysis is built on:

| Source | Access | Notes |
|---|---|---|
| `spec/PCIP_Proposal_V2.md` (683 lines) | **Read in full** | This is the target. |
| README (cached snapshot) | Read in full | **Stale.** Shows 24 commits, "MIT", "Next.js 14". |
| Live repo metadata (PR list, Issues, Discussions) | Read | **Newer than the README snapshot:** repo description now says **AGPL-3.0**; Dependabot is bumping Next.js **16.2.x → 16.3.6** (opened 23 Sep 2026); **54 PRs** exist (2 open, 52 closed); Discussions enabled; a public site `readprism.app` is linked; 0 open issues; 5 stars. A search snippet shows the README was rewritten to position the product as *behavioral, explainable, honest and open*, built first for **developers who self-host and follow 50+ technical feeds**. |
| `docs/`, `extension/`, `.github/`, commit history, closed PRs, `readprism.app` | **Blocked** (robots) | I could not read them. |
| Actual source code | **Not read** | So I cannot say whether any feature really works. |

**Consequence:** the repo is very likely *further along* than the stale README suggests (52 closed PRs vs 24 commits in the snapshot), but nothing below asserts that a feature works or doesn't. Where I say "not evident" I mean *not mentioned in the README/spec mapping*. **Phase 0 of the plan is a code audit that turns every guess here into a verified status** (Spec Coverage Matrix in `PROGRESS.md`).

Facts I *did* verify against primary sources are marked ✅. Facts from third-party blogs (many are competitors' marketing pages, notably Readless) are marked ⚠️ — re-check on vendor pages before you publish any comparison.

---

## 1. Verdict in one page

**The idea is strong and the spec is unusually thorough.** The differentiator — behavioral ranking that is explainable and open — is still a real gap: Feedly's AI is rules/topic based and paywalled; Inoreader's AI is summarization; Folo has AI digests but not a learned per-user ranker. Nobody credible offers *open-source behavioral ranking with faithful explanations*.

**But six things would sink it if left as specified**, ordered by urgency:

1. ✅ **Your LLM is probably dead.** Groq shut down `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` on **16 Aug 2026** for free/developer tiers. The README names both. If the code still hard-codes them, every summary has been failing for ~5½ weeks.
2. ✅ **The embedding model can't read your long articles.** `all-MiniLM-L6-v2` truncates around 256 tokens, so "deep reads" are ranked on their first ~200 words.
3. **The cold-start plan needs other users**, and a self-hosted instance has one. The spec's "collaborative warmup" is a no-op for the exact audience you're targeting.
4. **The Suggestion signal (the spec's "purest signal") needs a pool of non-followed content**, and nothing in the README says where that pool comes from.
5. **Learning from a ranked list is biased** (people read what's on top). The spec has no impression logging, no exploration, no evaluation harness — so you can't *prove* the ranking is better than chronological.
6. **Security basics for a self-hosted app that fetches arbitrary URLs and renders scraped HTML** (SSRF, XSS, XML bombs) — unverified in code, must be audited.

**The market moved since the proposal was written** (Feb 2026): Inoreader now has AI, Folo is an open-source AI reader with 33k+ stars, Pocket and Omnivore are gone, Feedly/Readless pricing changed. The proposal's competitor table and pricing are stale.

**Recommended strategy:** niche-first (developers who self-host), lean footprint, prove ranking quality with an eval harness, fix reliability/security first, then ship v0.1.0 publicly. Defer hosted tiers/teams.

---

## 2. Where we stand — spec vs. repo (as far as visible)

Legend: 🟢 README claims it · 🟡 partially/unclear · 🔴 not evident · ⚪ unknown (blocked folder). *Nothing here is verified in code.*

| Spec phase / item | README evidence | Status |
|---|---|---|
| **Phase 1 – Ingestion**: RSS/Atom, scraping (trafilatura+Playwright), newsletter forwarding, email digest | Listed in "What it does" + services (Browserless, Resend) | 🟢 |
| Chronological feed with manual categorization | Not mentioned | 🟡 |
| Fault tolerance + user notification | "Honest platform tiers" only | 🟡 |
| **Phase 2 – Ranking**: embeddings, 8-signal PRS, telemetry, explicit feedback, source trust, summaries, dedupe | All listed; migration 0003 = reading telemetry; `useReadingTelemetry` | 🟢 |
| Collaborative cold-start warmup | Listed (`cold_start/collaborative.py`) — but see Finding F4 | 🟡 |
| **Phase 3 – Advanced**: meta-learning weights, 3-scale temporal, serendipity, creator resolution, interest graph | Listed (`meta_weights.py`, `interest_graph/`, `creator/`) | 🟢 |
| Cross-source synthesis / emerging topics | Not mentioned | 🔴 |
| Explainability ("why this") | Claimed in concept; UI unknown | 🟡 |
| **Phase 4 – Ecosystem**: PWA/offline/push | Not mentioned | 🔴 |
| Browser extension | `extension/` folder exists — contents unknown | ⚪ |
| Obsidian/Notion/Logseq | Not mentioned | 🔴 |
| Discover-new-sources | Not mentioned | 🔴 |
| Self-host docs | `docs/` exists — contents unknown | ⚪ |
| Team digests, tiered pricing | Not applicable to self-host | — |
| Search (spec: Meilisearch) | Not in stack table | 🔴 |
| Digest length personalization, 30% saturation cap, digest sections | Sections claimed; others not mentioned | 🟡 |

**Rough read:** Phases 1–3 of the spec look largely built at a first-pass level; Phase 4 and the "second-order" features (synthesis, discovery, search, PWA, integrations) look open. The larger risk is not missing features — it's **correctness and evaluability of what exists** (Findings F1–F8).

---

## 3. Findings that change the plan

Each finding lists evidence → consequence → action (task IDs in `PROGRESS.md`).

### F1 — LLM model deprecation ✅ (P0)
Groq's deprecation page lists both `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` with a shutdown date of 16 Aug 2026 and suggests `openai/gpt-oss-120b` and `openai/gpt-oss-20b`. `qwen/qwen3.6-27b` was itself shut down on 14 Sep 2026 in favor of `qwen/qwen3.8-27b`. Other projects report 404s since the Llama shutdown. Free-tier limits are per-minute token caps (≈6k–12k TPM), which is the real constraint for a summarizer.
**Action:** provider-agnostic client, configurable model IDs, rate limiter, extractive fallback so the digest never depends on an LLM → **P0-05**. Decision **D-01/D-02**.

### F2 — Security surface of a URL-fetching, HTML-rendering app (P0, unverified)
Any app that fetches user-supplied URLs server-side (feeds, scraper, Browserless, link unwrapping) and renders third-party HTML in a reader/email needs: SSRF protection (block private/loopback/metadata IPs on every redirect), HTML sanitization + CSP, XML entity/expansion protection for feeds/OPML, auth hardening. I could not inspect code, so these are audit items, not accusations.
**Action:** **P0-06 / P0-07 / P0-08 / P0-09**.

### F3 — Embedding truncation ✅ (P1)
The all-MiniLM-L6-v2 family truncates input at ~256 word pieces by default; `nomic-embed-text-v1.5` supports 8k context at 768 dimensions (Matryoshka down to 64) and beats MiniLM on MTEB (≈62 vs ≈56); `bge-m3` covers multilingual + 8k. Nomic needs task prefixes (`search_document:` / `search_query:`); missing them silently degrades quality. Switching dimension means a migration (new column/table, dual write, backfill, cut-over).
**Action:** abstraction + golden retrieval check + migration → **IQ-01/02/03**. Decision **D-03**. Keep MiniLM as a `lite` profile for low-RAM boxes.

### F4 — Cold start can't use "other users" in a self-hosted install (P1)
Spec Mechanism Two (collaborative filtering) requires a population. Self-hosted = population of one.
**Action:** starter packs (curated OPML per topic), LLM interest expansion, imports from other readers, shipped topic priors, calibration on the user's *own* ingested items; keep collaborative code behind a flag that is a safe no-op below N users → **CS-01..05**. Decision **D-06**.

### F5 — The "purest signal" has no source of candidates (P1)
Suggestion-driven reading needs content from sources the user does *not* follow. README ingestion covers followed sources/creators only.
**Action:** a **discovery corpus** — outbound links from followed items, curated seed feeds per topic, optional public aggregator feeds (HN/Lobsters/arXiv listings) used purely as candidate sources; ANN from interest medoids; tag `origin=discovery` → **IQ-06**, later **EC-06** (suggest new sources).

### F6 — One mean interest vector dilutes multi-topic users (P1)
Pinterest's PinnerSage showed that a single embedding per user merges unrelated interests; clustering engaged items (Ward), representing each cluster by a real item (medoid), and sampling clusters by importance beat single-vector systems in production. A developer who reads Rust *and* urban planning *and* chess is the norm here.
**Action:** multi-interest profile as the semantic signal; interest graph stays as the explainable layer → **IQ-05**. Decision **D-05**.

### F7 — Feedback loop bias + no way to prove quality (P0/P1)
Users interact more with items shown higher; naively training on that reinforces the ranker's own choices. Standard remedies: log impressions with positions, add a little randomized exploration to estimate position effects, inverse-propensity weighting (clipped, because variance is high). Independent of that, the project has no evaluation harness — you can't claim "better than chronological" without one.
**Action:** impression logging, label definitions, exploration slots, clipped IPW, **synthetic-user simulator + replay metrics + CI thresholds** → **IQ-07/08/09/16**.

### F8 — Spec ambiguity that can cause target leakage (P0)
"Reading Depth" is a *scoring signal* for an item the user hasn't read yet. If it uses that item's own telemetry it is circular. It must be a **prediction** (from history on similar source × topic × length) and labels must come only from post-consumption events. Same for "Explicit Feedback".
**Action:** feature contract + leakage test → **IQ-04**. Weight learning: per-user, but with shrinkage to a prior and a minimum-evidence gate (sparse data), simplex-projected → **IQ-10**.

### F9 — Competitive landscape moved ⚠️ (strategy)
See §4. The moat is *behavioral + explainable + open + self-hostable*, not "has AI".

### F10 — Platform coverage: don't hand-build every connector (P1)
Reddit `.rss`, Substack `/feed`, Bluesky/Mastodon profile RSS, YouTube channel feeds still work; RSSHub is a large maintained route network. X/Twitter and LinkedIn stay honestly unsupported.
**Action:** native recipes first → optional RSSHub bridge → scraping → **IN-04/05/06**. Decision **D-11**.

### F11 — Footprint (P2)
Seven services and ≥4 GB RAM is heavy for hobbyist self-hosters (Miniflux runs in tens of MB). Postgres FTS + pgvector can replace Meilisearch initially; a `lite` profile (no Browserless, MiniLM) widens the audience.
**Action:** **UX-11**, **RL-01**. Decision **D-09**.

### F12 — Drift between README, LICENSE, spec, reality (P1)
README snapshot says MIT; repo description says AGPL-3.0; README says Next 14 while Dependabot targets Next 16.x; competitor and pricing tables in the spec are stale.
**Action:** **P0-10 / P0-13 / RL-08**; owner decision **OQ-01**.

### F13 — Email can't measure reading (P1)
Email gives no scroll depth. The loop that makes ranking learn is: email → one-click signed feedback + click-through into the in-app reader (telemetry). Tracking pixels are unreliable and privacy-hostile; leave off by default.
**Action:** **UX-04 / UX-05**.

### F14 — Hosted tiers/pricing are premature (strategy)
Artifact (Instagram founders' personalized news app) shut down citing insufficient market size for a standalone consumer app, and Yahoo took the technology. Read that as: the *engine* is valuable, the mass-market app is a hard business. Niche-first, open source, self-host; treat pricing/teams as backlog (**D-10**).

---

## 4. Competitive landscape (Sept 2026)

Prices from third-party sources ⚠️ unless noted — verify on vendor sites before publishing.

| Product | What it is now | Price (indicative) | AI / personalization | Gap vs ReadPrism thesis |
|---|---|---|---|---|
| **Feedly** | Polished cloud reader; Leo AI on Pro+ | Pro ≈ $6.99/mo; Pro+ ≈ $12.99/mo (≈ $8.25 annual) ⚠️ | Leo: topic/keyword prioritization, muting, dedupe, summaries — *user-trained*, no behavioral learning | No learned per-user ranker, no explanations, AI paywalled, closed |
| **Inoreader** | Power-user reader, rules, monitoring | Free (150 feeds); Pro $7.50/mo annual, $9.99 monthly ✅ | **Now has AI** (Intelligence since Mar 2025: summaries, reports; bring-your-own-AI key since Apr 2026) ⚠️ — *the V2 proposal's "no AI layer whatsoever" is outdated* | AI = summarization/Q&A, not behavioral ranking |
| **Readwise Reader** | Read-later + RSS + highlights + spaced repetition | ≈ $9.99/mo annual, $12.99 monthly; no free tier ⚠️ | Ghostreader (summaries, Q&A) | Optimizes retention of what you read, not deciding what to read |
| **Readless** | AI digest of newsletters + RSS, cross-source dedupe | ≈ $4.90/mo ⚠️ (spec said $9) | Summary digest, no learned ranking | Chronological/curated digest, no per-user model |
| **Folo** | **Open-source** AI RSS reader, 33k+ stars, all platforms, RSSHub-friendly | Free / cheap hosted ⚠️ | AI summaries, timeline TL;DR, daily AI digest, feed discovery | **Closest OSS rival.** No evidence of a learned, explainable per-user ranker |
| **Miniflux / FreshRSS** | Self-hosted readers; Fever + Google Reader APIs so Reeder/NetNewsWire work | Free (self-host) | None | No ranking; but they own the self-hoster mindshare |
| **NewsBlur** | Reader with training + (2026) Ask AI and Daily Briefing ⚠️ | ≈ $99/yr top tier ⚠️ | Intelligence trainer + AI briefing | Rule-like training, not embeddings/behavior |
| **Artifact** | Personalized news app (shut down Jan 2024; tech to Yahoo) ✅ | — | ML recommendations | Cautionary tale on market size |
| **Pocket / Omnivore** | Sunset 8 Jul 2025 / 15 Nov 2024 ⚠️ | — | — | Displaced users looking for an owned alternative |

**What this implies**
- Position on: *ranks by how you actually read · explains itself · open source · self-hostable · full engine free*. (README already says this; keep it.)
- Table-stakes to match: OPML import/export, decent full-text extraction, mobile-friendly reader (PWA), keyboard shortcuts, search, newsletters.
- Wedge worth a decision gate (EC-07): self-hosters already run Miniflux/FreshRSS. Either expose a Fever/Google-Reader-compatible API returning *ranked order* (so Reeder/NetNewsWire show your ranking) or a **sidecar mode** that imports subscriptions/read-state from those servers. Potentially the highest-leverage adoption move; cost unknown → ADR first.

---

## 5. Technical best-practice decisions

### 5.1 Feed fetching & parsing
- **Parsing is not the bottleneck; networking etiquette is.** Python `feedparser` (6.0.x) is fine. A Rust binding (`feedparser-rs`, ~90× faster) exists but is young (0.5.x) — not worth the risk now.
- Do: conditional GET (ETag/Last-Modified/304), gzip/br, honest User-Agent, adaptive per-feed polling from observed cadence (15 min–24 h, jitter), exponential backoff, honor `Retry-After`/429, treat 410 as dead and permanent 301 as URL rewrite, per-host politeness, WebSub where a hub is advertised (later), visible feed-health state. (**IN-01..03**)
- Identity/dedupe order: `(source, guid)` → canonical URL (strip `utm_*`/`fbclid`, honor `rel=canonical`) → content simhash → embedding+title similarity across sources. (**IN-07**)
- Autodiscovery: `<link rel="alternate">` → well-known paths → platform recipes → RSSHub → scrape. (**IN-04**)

### 5.2 Full-text extraction (the "best way of parsing")
- Benchmarks (WCXB 2026, Zyte, SIGIR'23): **Trafilatura** is the best widely-used Python option overall (article F1 ≈ 0.92 on the multi-type set, ≈ 0.9+ on news benchmarks); Mozilla Readability has excellent *median* but weaker mean; newspaper4k is close on news but lags on other page types. All heuristic extractors are **weak on forums, listings, collections, product pages** (F1 ≈ 0.5–0.7) → classify page type and **don't rank non-articles**.
- Newer options (rs-trafilatura with an ML page-type classifier; a fine-tuned small-model fallback "MinerU-HTML") report the best held-out scores — track them, but adopt only if they beat Trafilatura on **your own golden corpus**.
- **Cascade (IN-08):** feed full-content if long enough → Trafilatura → Readability fallback (pick by confidence) → Playwright render only if the page looks JS-only → visible failure state. Persist `extraction_method`, `extraction_confidence`, `page_type`.
- **Golden corpus (IN-09):** ≥100 URLs from your real feeds + short expected-snippet assertions; snapshot pages locally (don't commit third-party pages — copyright); CI runs an offline subset and fails on regressions.
- **Paywalls:** detect and label; never circumvent (D-08). **robots.txt:** honor in scrape mode.

### 5.3 Newsletters
Provider-agnostic inbound adapters (Cloudflare Email Routing + Worker is free; Postmark, Mailgun, Resend inbound all POST webhooks; IMAP poller for self-hosters), per-user plus/hash addresses, signature verification, MIME→HTML→sanitize→extract, tracking-pixel and link-wrapper stripping, `List-Unsubscribe`, confirmation-email detection, one Source per sender. (**IN-11/12**)

### 5.4 Platforms / creators
Native recipes: YouTube channel feed (resolve `@handle`→channel ID), Reddit `.rss` (still works in 2026), Substack `/feed`, Bluesky & Mastodon profile RSS, GitHub Atom, arXiv, podcasts (+ Podcast 2.0 transcript tag). RSSHub as optional bridge. X/LinkedIn: unsupported and labeled. (**IN-05/06**)

### 5.5 Embeddings & storage
`nomic-embed-text-v1.5` default after golden check; `bge-m3` multilingual; MiniLM `lite`. Build the embedded text from title + lead + body windows (pooled), store model/version per row, HNSW cosine index, dual-write migration. (**IQ-01..03**)

### 5.6 LLM layer
OpenAI-compatible `base_url`+`model`; Groq default `openai/gpt-oss-120b`/`-20b`; Ollama/OpenRouter/OpenAI/Anthropic-compatible endpoints supported; JSON-schema outputs; cache by `(content_hash, prompt_version, model)`; rate limiter sized to TPM; extractive fallback. (**P0-05**)

### 5.7 Ranking architecture (summary; full pseudo-code in the prompt §A3–A6)
1. **Candidates:** followed recents ∪ ANN neighbors of interest medoids in a discovery corpus ∪ exploration sample.
2. **Score:** `PRS = Σ wᵢ·fᵢ` over 8 pre-consumption features; `w` per user learned online (pairwise logistic, L2 shrinkage to prior, min-evidence gate, simplex projection); short-term saturation as a multiplier.
3. **Re-rank:** MMR (λ≈0.7) + 30% cluster cap + novelty slots (15%, adaptive) + 1–2 randomized exploration slots (logged propensity).
4. **Explain:** exact `wᵢ·fᵢ` contributions + top matching interest cluster(s) — faithful by construction because the model is linear.
5. **Evaluate:** replay metrics + synthetic-user simulator in CI.

### 5.8 Security & privacy
SSRF-safe `safe_fetch()` for every outbound URL; server+client sanitization + CSP; XML hardening; argon2id/bcrypt, token rotation, rate limits, CORS lock, boot-time secret check; no third-party telemetry; privacy doc listing what leaves the box (LLM provider, email provider, optional RSSHub); export/delete-my-data. (**P0-06..09, UX-13, RL-02**)

---

## 6. Roadmap

Time estimates assume one focused human-plus-agent workflow; treat them as relative sizing, not promises.

| Phase | Goal | Key tasks (see `PROGRESS.md`) | Exit gate (measurable) | Rough size |
|---|---|---|---|---|
| **0 — Audit & Stabilize** | Know the truth; stop the bleeding | P0-01..13 | Coverage matrix complete; LLM client fixed; SSRF/XSS/XML suites green; CI green; docs match reality | ~1 week |
| **1 — Ingestion hardening** | Never miss, never garbage | IN-01..18 | Article-type extraction F1 ≥ 0.90 on golden corpus; ≥95% extraction success; polling+health verified; ≥2 newsletter providers + IMAP | 2–3 weeks |
| **2 — Intelligence v2** | Provably better than chronological, and explainable | IQ-01..18 | Eval report beats chronological/semantic-only/random on synthetic users; embedding ADR + tested migration; 100% impressions logged; faithful explanations | 3–4 weeks |
| **3 — Digest & reader UX** | Feels smart daily | UX-01..15 | Sections/length/scheduling/email v2 with signed feedback; search meets latency; a11y CI | 3 weeks |
| **4 — Cold start w/o population** | First digest already good | CS-01..06 | First-digest gate passes for ≥5 synthetic personas | 1–2 weeks |
| **5 — Ecosystem** | Fit into people's workflows | EC-01..08 | PWA installable+offline; extension packaged; API tokens + MCP documented | 3 weeks |
| **6 — Release & community** | Public v0.1.0 | RL-01..08 | Fresh-VM install ≤10 min; backup/restore proven; docs live; tag | 1–2 weeks |

**Sequencing rules**
- Nothing in Phase 2 ships to users before **IQ-07/08/16** (logging, labels, eval) exist — otherwise you're tuning blind.
- **IQ-04 (feature contract)** before **IQ-10 (weight learning)**.
- **P0-06/07** before any new ingestion or reader work touching external content.
- Consider pulling **UX-04 (email feedback links)** forward: it's the highest-yield source of learning signal.

**Now / Next / Later** (updated 2026-09-24 to match `docs/PROGRESS.md`; the phase table above is the original plan)

- **Now:** owner review of Phase 0. Still open inside the phase: P0-11 (CI green on `main`) and P0-12 (Dependabot #53 and #54).
- **Next:** IN-01 (conditional GET), then the rest of ingestion. IQ-07/08/16 and IQ-04 stay ahead of weight learning, as in the sequencing rules.
- **Later:** IN-08/09 tuning once the golden corpus exists, then ecosystem, the sidecar decision, the docs site, v0.1.0.

---

## 7. Success metrics

| Metric | Target for v0.1.0 | How measured |
|---|---|---|
| Ranking quality vs chronological (synthetic users, NDCG@10) | Statistically clear win; threshold in eval report | `make eval` |
| Lead-section open rate (real use, opt-in local stats) | Trending up over first 4 weeks per user | local admin page |
| Extraction success (article pages) | ≥ 95% success, F1 ≥ 0.90 | golden corpus |
| Ingest→scored latency p95 | < 60 s | metrics |
| Digest build time | < 3 s / 1,000 candidates | benchmark |
| Time to first useful digest | < 10 min from fresh install | CS-05 + install test |
| Fresh install time (Lite profile) | ≤ 10 min, ≤ ~2 GB RAM | RL-01 |
| Explanation faithfulness | 100% of ranked items | test |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Scraper/site breakage is perpetual | Golden corpus + health UI + cascade; treat as maintenance, not a project |
| LLM/provider churn (already happened) | Provider-agnostic client, fallback, no hard-coded IDs |
| Sparse per-user data | Shrinkage to prior, min-evidence gate, exploration, starter packs |
| Feedback-loop bias / filter bubble | Exploration slots, IPW, adaptive serendipity, novelty share |
| Privacy expectations | No third-party telemetry, docs on data flows, export/delete |
| Scope creep (7 services already) | `lite` profile, Postgres FTS first, defer hosted/team |
| Folo/Feedly add behavioral ranking | Lean on openness, explainability, eval transparency, self-host |
| Legal (scraping, paywalls, licenses) | Honor robots in scrape mode, never bypass paywalls, license report |

---

## 9. Decisions I assumed (change any in `PROGRESS.md` §2–3)

1. Target user = developers who self-host (matches the repo's current positioning).
2. Keep the existing `LICENSE` file as truth; README to be corrected (OQ-01).
3. No hosted/billing work until there's real pull.
4. Groq stays the default LLM provider; Ollama documented as the local option.
5. Postgres FTS before Meilisearch.

---

## 10. Sources

Repo & spec: github.com/mohitmishra786/readprism (README snapshot, `/pulls`, `/issues`, `/discussions`, `spec/PCIP_Proposal_V2.md`).
- Groq deprecations (✅ primary): console.groq.com/docs/deprecations
- Feedly pricing/AI: makerstack.co/reviews/feedly-review · readless.app/compare/readless-vs-feedly ⚠️ (competitor page)
- Inoreader pricing/AI: inoreader.com/pricing · readless.app/blog/inoreader-pricing-2026 ⚠️
- Readwise Reader: marqly.com/blog/readwise-reader-review-2026 · readless.app/blog/readwise-reader-pricing-2026 ⚠️ (also source for Pocket/Omnivore shutdown dates)
- Folo: github.com/RSSNext/Folo · news.ycombinator.com/item?id=46033915 · RSSHub: github.com/diygod/rsshub
- Miniflux/FreshRSS: ossalt.com/guides/freshrss-vs-miniflux-2026
- Artifact: medium.com/artifact-news/shutting-down-artifact-1e70de46d419
- Extraction: github.com/Murrough-Foley/web-content-extraction-benchmark · arxiv.org/pdf/2605.21097 · dl.acm.org/doi/pdf/10.1145/3539618.3591920 · contextractor.com/trafilatura-vs-readability-vs-newspaper
- Embeddings: morphllm.com/ollama-embedding-models · d-central.tech/local-embedding-models · arxiv.org/pdf/2402.01613 (Nomic)
- PinnerSage: arxiv.org/pdf/2007.03634
- Position bias / IPW: arxiv.org/pdf/1608.04468
- Reddit RSS: wprssaggregator.com/reddit-rss-feed · Bluesky/Mastodon/Substack/YouTube feed patterns: nutshellnewsletter.com/blog/what-is-rss-and-why-it-still-matters
- feedparser-rs: pypi.org/project/feedparser-rs
- Inbound email options: sequenzy.com/blog/best-free-inbound-email-apis · mailtrap.io/blog/best-inbound-email-api
- GLM-5.3: datanorth.ai/news/z-ai-releases-glm-5-3 · innfactory.ai/en/ai-models/glm
