# 17 — KPI & Metrics Framework

*The tie-together artifact. 2–4 metrics per audit angle with target thresholds. Built last, on top of artifacts 01–16. Evidence: repo state (no analytics exist yet) + spec targets.*

## Status Snapshot

- **There is currently no analytics, no metrics endpoint, and no dashboard in the codebase.** Every metric below is net-new instrumentation. This is the single biggest measurement gap: a personalization product with zero measurement of personalization quality.
- Thresholds are marked **[baseline-first]** where you should measure before committing to a target (most of them) vs **[hard]** where an absolute bar is justified.
- The one metric that matters most across every angle is **suggestion-driven-read rate** — the spec's "purest signal" and the leading indicator that the wedge works.

## Metrics by angle

**A. Strategy / PMF (artifacts 01–03)**
- Suggestion-driven read rate = reads where `was_suggested=true` ÷ total reads. **Target: >0 for ≥50% of users by day 7; ≥15% of all reads by day 90 [baseline-first].** *The* PMF metric.
- Day-30 cohort retention (opened ≥1 digest in last 7d). **Target [baseline-first]; compare to NewsBlur/Feedly-class ~20–30% D30 as sanity.**
- Onboarding→first-value conversion (finished onboarding AND opened ≥1 first-digest item). **Target ≥60% [baseline-first].**

**B. Technical (artifacts 04–08)**
- PRS ranking quality: rank-correlation / read-prediction AUC between predicted PRS and actual next-day reads, per cohort. **Target: AUC > 0.6 and rising week-over-week [baseline-first].** Without this, "it learns" is unfalsifiable.
- Meta-weight divergence: mean |learned − default| weight per active user over time. **Target: measurably rising (proves personalization is happening, not inert).**
- Scraper success rate per source per week. **Target ≥95% [hard]; alert < 85%.**
- P95 API latency + event-loop stall incidents. **Target P95 < 500ms [hard] for read endpoints.**

**C. Design/UX (artifacts 09–10)**
- Onboarding completion rate (started→finished 5 steps). **Target ≥70% [baseline-first]; if low, the trim in artifact 10 is validated.**
- Day-7 digest open rate. **Target ≥40% of D7-retained users [baseline-first].**
- Reader engagement: median scroll depth + active time per opened item (telemetry already captured). **Target: median completion ≥0.5 [baseline-first].**
- Feedback participation: % of active users giving ≥1 explicit signal/week. **Target ≥25% [baseline-first]** (fuels the learning loop).

**D. Growth (artifacts 11–13)**
- GitHub stars velocity + unique clones/week (launch signal). **Target: 200 stars in 30 days post-Show-HN [baseline-first].**
- Organic: comparison-page impressions + branded search volume (post marketing-site). **Target: rank top-10 for "open source feedly alternative" in 90 days [baseline-first].**
- Free→Pro conversion (once billing exists). **Target 1–5% of active users [hard-ish, OSS-SaaS benchmark].**
- CAC by channel (organic vs any paid) — pre-launch keep paid at $0; track organic cost-per-signup as founder-time.

**E. Timeline / Ops (artifacts 14–16)**
- Launch-day: signups, error rate (Sentry), infra saturation. **Target: error rate < 1% [hard]; zero unhandled outages.**
- Cold-start funnel completion (signup→onboard→first-open→D7). **Instrument before launch [hard requirement].**
- Iteration cadence: shipped-vs-planned per month. **Target: no >4-week silent gaps [hard]** (history shows one).

**F. Measurement / Economics (artifacts 07/13)**
- Real per-user LLM cost + summary-cache hit rate. **Target: cache hit ≥60% [baseline-first]; per-Pro-user LLM < $0.50/mo.** Directly validates or breaks the unit-economics model.
- Email deliverability: delivery rate + spam-complaint rate. **Target: delivery > 95%, complaints < 0.1% [hard]** ([Resend guidance](https://resend.com/blog/top-10-email-deliverability-tips)).
- Infra $/active-user/month. **Target [baseline-first]; must trend below Pro price × conversion.**

## Instrumentation priority (what to build first)

1. **Event pipeline** capturing: signup, onboarding step/complete, digest generated, digest-item opened, read telemetry (exists — surface it), explicit feedback, `was_suggested` reads. (P0)
2. **Cohort retention + cold-start funnel** view. (P0)
3. **Ranking-eval harness** (offline, per cohort). (P1)
4. **Cost/cache + scraper-health** dashboards. (P1)
5. Growth/SEO tracking (GitHub insights + Search Console once site exists). (P2)

## Checklist

- [ ] P0 | Build the core event pipeline (self-hosted analytics e.g. PostHog/Plausible + DB events) | Nothing below is measurable without it | no analytics in repo | M | eng
- [ ] P0 | Ship the cold-start funnel + D1/D7/D30 cohort dashboard before launch | The launch traffic is the one chance to measure it | none | M | eng
- [ ] P0 | Define suggestion-driven-read rate as the North Star and put it on the dashboard | Single best flywheel/PMF indicator | `was_suggested` column exists | S | eng
- [ ] P1 | Ranking-eval harness (PRS→read AUC per cohort), reviewed weekly | Makes "it learns" falsifiable | artifact 05 | M | eng
- [ ] P1 | Cost + summary-cache-hit + scraper-success dashboards with alerts | Validates economics + catches silent decay | artifacts 07/13 | M | eng
- [ ] P1 | Email deliverability monitoring (delivery + complaint rate) | Protects the one retention channel | `utils/email.py` | S | eng
- [ ] P2 | Growth tracking (stars/clones, Search Console) once marketing site ships | Attribute what works | artifact 11 | S | founder
- [ ] P2 | Set the [baseline-first] targets after the first cohort produces baselines | Avoid inventing thresholds | this artifact | S | founder

## Top 5 if you only do 5 things

1. Build the event pipeline — it's the prerequisite for every other metric here.
2. Ship the cold-start funnel + cohort-retention dashboard before launch.
3. Make suggestion-driven-read rate the North Star metric.
4. Build the ranking-eval harness so "it learns" is falsifiable.
5. Track real LLM cost + cache-hit rate to validate (or break) the economics.

**Revisit trigger:** re-run once the event pipeline is live and the first cohort produces baselines — then set the [baseline-first] targets for real.
