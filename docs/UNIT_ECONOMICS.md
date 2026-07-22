# Unit Economics (re-modeled, July 2026)

*Replaces the spec's optimistic $0.31 free / $0.95 Pro / 81%-margin table with
real 2026 provider pricing and explicit assumptions (audit 07-5 / 13-2). Numbers
are directional, not a guarantee — the load-bearing variable is the summary
cache-hit rate.*

## Provider prices used

- **Groq Llama 3.3 70B:** ~$0.59 / M input tokens, ~$0.79 / M output tokens
  ([groq.com/pricing](https://groq.com/pricing)). Batch/prompt-caching can cut
  this ~25–50%.
- **Email (Resend):** free 3,000/mo (100/day), then $20/mo for 50k
  ([resend.com/pricing](https://resend.com/pricing)). A **step cost**, not linear.
  (The shipped code uses generic SMTP / Zoho; the same step-cost logic applies —
  Zoho's own send limits kick in earlier.)
- **Embeddings:** local sentence-transformers, no API cost — but CPU time is the
  worker bottleneck, not a line item.

## The load-bearing assumption: summary cache-hit rate

Summaries are cached across all users of a shared source (`summarization_cached`,
shared `content_items`). Whether the economics work hinges almost entirely on how
often a summary is already cached when a user needs it:

- **Popular sources** (many co-subscribers) → high cache hits → low marginal LLM
  cost.
- **Niche sources** (few co-subscribers) → low cache hits → the summary is paid
  for nearly every user. This is exactly ICP #1's (deep-niche self-hoster)
  reading pattern, so **assume a *lower* cache-hit rate for the core ICP.**

Model it explicitly. Rough per-Pro-user monthly LLM cost, assuming ~300 summarized
items/mo at ~1.5k input + 0.3k output tokens each (~0.9M in / 0.09M out before
caching ≈ $0.53 + $0.07 ≈ $0.60 uncached):

| Cache-hit rate | Effective LLM $/Pro-user/mo |
|---|---|
| 80% (mostly popular sources) | ~$0.12 |
| 60% | ~$0.24 |
| 40% (niche-heavy, ICP #1) | ~$0.36 |
| 0% (worst case) | ~$0.60 |

Target from the KPI framework: **cache hit ≥ 60%, per-Pro-user LLM < $0.50/mo.**

## Email is a step cost, not $0.02/user

- 1 daily digest/user hits Resend's 100/day free cap at ~100 users.
- $20/mo then covers ~50k sends ≈ ~1,600 daily-digest users.
- So email is flat within a tier and jumps at tier boundaries — don't model it
  as linear per-user.

## Free vs Pro alignment (see audit 13)

Giving the full ranking engine + LLM summaries away on Free means cost scales with
free users while revenue doesn't. Recommended lever: **Free = cached/shared
summaries only; Pro = on-demand, detailed, per-item synthesis**, which ties the
paywall to the variable cost. Heavy/niche users are pushed to self-host with their
own Groq key (they pay their own inference).

## Realistic near-term target

Not the spec's 8,000-Pro profitability endgame. Model a **hosted beta under
$100/mo infra serving < 100 users**, and instrument real per-user LLM cost +
cache-hit rate from that beta (KPI framework, artifact 17) before projecting
further.
