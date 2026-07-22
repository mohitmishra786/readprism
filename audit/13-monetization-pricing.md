# 13 — Monetization & Pricing Audit

*Evidence: spec §Pricing/§Unit Economics + code (tier field, digest rate-limit) + current LLM/email/infra pricing (web search July 2026).*

## Status Snapshot

- Pricing tiers exist in the model (`users.tier` = free/pro/…) and a free-tier digest-generation rate limit is enforced (`RATE_LIMIT_FREE_MINUTES=60`), but **no billing integration exists** (no Stripe, no entitlement enforcement beyond that one throttle). Monetization is spec-only.
- **The pricing philosophy is internally contradictory with the cost structure.** Spec: "gating the ranking engine would contradict the premise → full engine is free." But the ranking engine (LLM summaries + embeddings + PRS precompute) *is the main variable cost*. Giving away the expensive part free and charging for source *quantity* means costs scale with free users while revenue doesn't.
- The $4.99 Pro undercuts incumbents but sits **above** 2026 budget AI-digest entrants (Brief Digest $2.99, Meco $2.92/yr-equiv) — so "cheap" is no longer differentiated on price alone.
- The 8,000-Pro profitability math rests on a summary-cache hit rate that the **niche-reader ICP structurally undermines** (niche sources = few co-subscribers = poor cache hits).

## Pricing stress test

**Free = full ranking + summarization, 30 sources / 5 creators, 1 digest/day.** The costly operations (Groq summaries, embeddings, PRS) all run for free users. The only lever pulled at Free→Pro is *quantity* (sources/creators/frequency), not the expensive *intelligence*. Result: a heavy free user on 30 niche sources can cost more than a light Pro user. That's backwards.

**Cost reality (2026, from artifact 07):**
- Groq Llama 3.3 70B: $0.59/M in, $0.79/M out ([groq.com/pricing](https://groq.com/pricing)); batch/cache can cut to ~25–50%. Viable *only* with high cross-user summary-cache hits.
- Resend: free 3k/mo (100/day), then $20/mo/50k — a **step cost**, not linear ([resend.com/pricing](https://resend.com/pricing)). Daily digests hit the 100/day free cap at ~100 users.
- Embeddings free per-call but CPU-bound = the worker bottleneck (solo pool).

**The spec's $0.31 free / $0.95 Pro and 81% margin are optimistic**; directionally the model can work *if and only if* summary caching hits hard — which conflicts with the niche-ICP. For ICP #1 (deep niche), expect worse cache rates and higher per-user LLM cost.

## Recommendation: change what gates Free→Pro

Keep the philosophically-right "ranking is free," but gate on the things that (a) cost you money and (b) signal power-user value:

1. **Digest frequency & synthesis** — Free: 1/day, no cross-source synthesis; Pro: up to 4×/day + synthesis + serendipity controls (spec already proposes this — good, keep it).
2. **Source/creator limits** — keep, but they're weak levers (easy to sit under).
3. **Add a real cost-aligned lever:** summarization *freshness/depth*. Free users get cached/shared summaries only (great — aligns cost with the cache that makes economics work); Pro users get on-demand, detailed, per-item synthesis. This directly ties the paywall to the variable cost.
4. **Self-hosted = bring-your-own-Groq-key** (already the plan) — this is the correct pressure-release: heavy/niche users self-host and pay their own LLM bill. Lean into it.
5. **Consider usage-based reality:** the 2026 OSS-SaaS trend is usage-based + managed hosting, not seat pricing ([OSS monetization 2026](https://blog.mean.ceo/open-source-monetization-trends-july-2026/)). A "hosted convenience" premium (you manage Postgres/Groq/scraping) is the honest pitch for ICP #2.

**Price point:** $4.99 is defensible against incumbents but market it on *capability* (behavioral ranking) not price, since Brief Digest/Meco are cheaper. Don't race Brief Digest to $2.99 — you can't win a cost war while giving away LLM inference.

## Profitability reality

- Conversion benchmarks: hosted-SaaS-from-OSS ~1–5% of active users; median OSS→$1M ARR is 3–5 years ([OSS monetization](https://earnifyhub.com/blog/open-source-monetization-making-money-from-free-software)).
- 8,000 Pro subs implies a large free base (say 5% conversion → 160k free users) each incurring LLM+email+compute. The spec's ~$8k/mo infra at that scale is almost certainly low once you add managed Postgres, email step costs, and worker sharding off the solo pool.
- **Realistic near-term goal isn't profitability — it's sub-100-user validation + a hosted beta with <$100/mo infra.** Model that, not the 8k-sub endgame.

## Checklist

- [ ] P0 | Re-align the Free/Pro boundary with variable cost: Free = cached/shared summaries + 1 digest/day; Pro = on-demand synthesis + frequency | Today Free gives away the expensive part; costs scale with free users | spec §Pricing; `tier` field; no entitlement code | M | founder
- [ ] P1 | Rebuild the unit-economics model with real Groq/Resend numbers + an explicit cache-hit assumption + step costs | Spec table won't survive scrutiny and misguides the roadmap | spec §Unit Economics; artifact 07 | M | founder
- [ ] P1 | Lean into self-hosted BYO-LLM-key as the pressure-release for heavy/niche users | Aligns your worst-margin users with their own cost | already the plan | S | founder
- [ ] P1 | Market Pro on capability, not price (don't chase Brief Digest's $2.99) | You can't win a price war while giving away inference | competitor pricing (search) | S | founder
- [ ] P2 | When billing is built, enforce entitlements server-side (not just the one digest throttle) | Tiers are currently unenforced beyond rate limit | `api/digest.py` rate limit only | M | eng
- [ ] P2 | Model a "hosted convenience" premium framing for ICP #2 rather than seat pricing | 2026 trend favors managed-hosting value over seats | OSS-SaaS trend (search) | S | founder
- [ ] P2 | Set a realistic near-term financial target (hosted beta < $100/mo, <100 users) instead of 8k-Pro profitability | Keeps decisions grounded pre-PMF | spec profitability claim | S | founder

## Top 5 if you only do 5 things

1. Move the paywall onto the variable cost: free users get cached summaries, Pro gets on-demand synthesis.
2. Rebuild unit economics with real 2026 numbers and an explicit cache-hit assumption.
3. Push heavy/niche users to self-host with their own Groq key.
4. Sell Pro on behavioral-ranking capability, not on being cheapest.
5. Replace the 8k-Pro fantasy with a <100-user, <$100/mo hosted-beta target.

**Revisit trigger:** re-run when billing is implemented and when you have real per-user LLM cost data from the hosted beta.
