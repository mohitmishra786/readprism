# 12 — Marketing & Positioning Audit

*Evidence: README, docs/LAUNCH.md, spec, competitor positioning (web search July 2026).*

## Status Snapshot

- **The name-adjacent tagline "Personalized Content Intelligence Platform" (PCIP) fails the 5-second test.** It's enterprise-generic; it could describe a martech analytics tool. It communicates category, not value, and not to the right audience.
- The README's actual one-liner is much better: *"ranks it by personal relevance using a continuously learning model… exactly what you need to read, in the right order, for you."* That's the real pitch — lead with it, drop "PCIP" entirely from external copy.
- `docs/LAUNCH.md` is genuinely strong — HN + r/rss copy that's honest, technical, and self-aware about cold start. This is the project's best marketing asset and it's launch-ready in tone. (It does contain a placeholder repo URL `github.com/readprism/readprism` that must be fixed, and claims AGPL while LICENSE says MIT — artifact 08.)
- Differentiation is real but **over-claimed** ("no existing tool does this"); the honest, defensible version is narrower and more credible.
- Channel fit is good for ICP #1 (HN, r/rss, r/selfhosted) and absent for ICP #2.

## Positioning

**Kill:** "Personalized Content Intelligence Platform." **Use externally:** something like —

> **ReadPrism — the reading app that ranks by how you actually read.**
> Aggregates every source and creator you follow, and orders your daily digest by personal relevance — a learning engine that gets sharper the more you read. Open source and self-hostable.

Three defensible, provable differentiators (all in the code today):
1. **Behavioral, not keyword** — scroll depth + active reading time, not rules you maintain (vs Feedly Leo).
2. **Explainable** — every item shows why it ranked; the interest graph names the connections (vs black-box algo feeds).
3. **Honest + open** — closed platforms marked unsupported, full engine free, self-hostable, source-available (vs SaaS black boxes).

Avoid: "no one does this" (NewsBlur/Particle exist), "AI" as a headline (commoditized in 2026 — every reader has summaries now), and the enterprise register of the spec.

## Content marketing plan (proportionate to a solo founder)

- **Flagship post (highest ROI):** "How we rank your reading: 8 signals + per-user gradient descent + a decaying interest graph." The transparency *is* the marketing — devs share honest ML write-ups, and it doubles as the SEO link magnet (artifact 11). Your competitors (hosted SaaS) structurally won't write this.
- **Cold-start post:** "The hardest problem in a personalization product, and how we're (honestly) tackling it." Matches the LAUNCH.md humility that HN rewards.
- **Cadence:** 1 substantial post/month is plenty solo. Don't start a content treadmill you can't sustain.

## Channel strategy (ranked for a solo/no-budget founder)

| Channel | Worth it pre-launch? | Notes |
|---|---|---|
| Show HN | **Yes — the launch event** | LAUNCH.md copy is ready; time it for a Tue–Thu morning ET; be present all day to answer |
| r/selfhosted, r/rss | **Yes** | ICP #1 lives here; LAUNCH.md has copy; lead with self-host + open source |
| GitHub (topics, README, Discussions) | **Yes** | Artifact 11; the durable discovery surface |
| Lobsters | Yes (if invited/has account) | Dev-quality audience, ML/show tags |
| Indie Hackers | Marginal | Build-in-public log; low cost, slow payoff |
| X/Bluesky dev communities | Marginal solo | Only if you already have presence; don't build a following from zero for this |
| Product Hunt | **Later, not first** | Better once hosted + polished; PH audience is design/consumer, not self-host |
| Newsletter-of-newsletters partnerships | Later | Only meaningful with a hosted product + real users |

## Checklist

- [ ] P0 | Replace "PCIP / Personalized Content Intelligence Platform" with the plain-value one-liner in all external copy | Current tagline fails the 5-second test with the target audience | README/spec title; LAUNCH.md is already better | S | founder
- [ ] P0 | Fix LAUNCH.md placeholder repo URL + AGPL/MIT claim before posting anywhere | Wrong URL/license in launch copy = credibility + legal problem | docs/LAUNCH.md | S | founder
- [ ] P1 | Write the flagship "how the ranking works" post; it's marketing + SEO + dev-trust in one | Your single most defensible, most shareable asset | code differentiators | M | founder
- [ ] P1 | Lock the 3 differentiators (behavioral / explainable / open) and use them verbatim everywhere | Consistent, provable claims beat broad "AI" claims | this artifact | S | founder
- [ ] P1 | Prepare a 60–90s demo GIF/video: onboarding → digest → why-ranked → interest graph | Every channel needs a visual; you have none | no media in repo | M | founder
- [ ] P2 | Drop "AI" from the headline; keep it in the body | "AI reader" is commoditized in 2026; behavioral+explainable is the wedge | market search | S | founder
- [ ] P2 | Build-in-public thread documenting the cold-start experiment (artifact 01) | Turns your biggest risk into honest content HN rewards | none | S | founder

## Top 5 if you only do 5 things

1. Retire "PCIP"; lead with "ranks by how you actually read."
2. Fix the LAUNCH.md URL + license claim, then it's ready to ship.
3. Write the transparent ranking-engine post (marketing + SEO + trust).
4. Lock the three provable differentiators and use them everywhere.
5. Record a 60-second demo — you cannot launch on any channel without one.

**Revisit trigger:** re-run after Show HN (what messaging actually resonated) and when a hosted product exists (Product Hunt / partnership channels open up).
