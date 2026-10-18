# 16 — Post-Launch / Retention & Iteration Checklist

*Turns the spec's narrative flywheel ("30 days better, 90 days indispensable, 1 year hard to leave") into measurable definitions. Evidence: spec §"Why the Ranking Engine Is Defensible" + code.*

## Status Snapshot

- The spec's retention story is **narrative, not instrumented**. None of the 30/90/365 milestones has a measurable definition or a metric in the codebase.
- The flywheel *depends on* the suggestion-driven-read signal (spec's "purest signal"); the DB records `was_suggested`, but there's no aggregate that tracks whether the flywheel is actually turning.
- The spec itself names the two retention killers: cold-start weakness and light-user thinness. Both are confirmed by the build (signals need 5–20 interactions). Retention work must target the first 14 days hardest.
- Scraping reliability is a named "continuous operational burden" — with no monitoring today, silent scraper decay will erode digest quality invisibly and drive slow churn.

## Turning the flywheel into measurable checkpoints

| Spec milestone | Proposed measurable definition | Instrumentation needed |
|---|---|---|
| "Day 30: noticeably better" | Digest-item open rate at day 30 ≥ 1.5× day 1 for the same cohort; suggestion-read rate > 0 for ≥50% of cohort | per-cohort daily open-rate + `was_suggested` reads |
| "Day 90: indispensable" | D90 retention (opened ≥1 digest in last 7d) ≥ [target]; ≥X% of reads are suggestion-driven | cohort retention curve + suggestion-read ratio |
| "1 year: hard to leave" | D365 retention ≥ [target]; interest-graph node count + meta-weight divergence from defaults (proxy for accumulated model value) | graph-size + weight-divergence per user |

Set the bracketed targets *after* the concierge test + first cohort give you a baseline; don't invent them.

## 30/60/90-day cadence

**Days 0–30 (survive cold start):**
- Daily: cold-start funnel (signup→onboard→first-digest-open→D1/D3/D7 return), error rate, scraper success rate.
- Weekly: read the qualitative feedback (thumbs-down reasons, `explicit_rating_reason` tallies) — these are your fastest quality signal.
- Ship: first-digest honest-state fix, onboarding trim, any cold-start quality fixes surfaced by the concierge test.

**Days 30–60 (prove learning):**
- Run the ranking-eval harness (artifact 05) per cohort: does predicted-PRS rank predict actual reads? Is it improving week-over-week per user?
- Monitor meta-weight drift — are weights actually diverging per user, or stuck near defaults (would indicate the learning is inert)?
- Ship: fixes to the averaged-interest-vector and meta-learning-leakage issues if eval shows weak ranking.

**Days 60–90 (retention + reliability):**
- Track D30 retention of the launch cohort; interview churned users (why they stopped).
- Stand up scraper-health monitoring; budget recurring time for scraper fixes (the spec's named burden).
- Roadmap-vs-actual review: the commit history shows a 4-month gap (Mar–Jun 2026) — set a sustainable solo cadence and hold it.

## Contingency: if cold start is weaker than hoped

The spec flags this as the top risk; pre-plan the response so you don't freeze:
- Lean harder on curated starter packs (expand `starter_sources`, human-curate per interest cluster).
- Add an explicit "not personalized yet — improving as you read" honesty banner for the first N days (sets expectations, buys patience).
- Consider a manual/editorial digest for week 1 while the model warms (concierge-style), then hand off to the engine.
- If suggestion-read rate stays ~0 after fixes, revisit the semantic-vector and serendipity-selection defects (artifacts 04/05) before concluding the wedge is wrong.

## Checklist

- [ ] P0 | Instrument cohort retention (D1/D7/D30) + the cold-start funnel | The entire retention thesis is currently unmeasured | no analytics in repo | M | eng
- [ ] P0 | Instrument suggestion-driven-read rate as the flywheel health metric | Spec's "purest signal" is the leading indicator of the moat | `was_suggested` exists; no aggregate | M | eng
- [ ] P1 | Build the per-cohort ranking-eval harness (does PRS predict reads?) and review weekly in days 30–60 | Distinguishes "it learns" from "it converges to noise" | artifact 05 | M | eng
- [ ] P1 | Scraper-health monitoring + a recurring maintenance time budget | Named continuous burden; silent decay → slow churn | `fetch_error_count` unused | M | eng
- [ ] P1 | Churned-user interview loop (trigger on 14d inactivity) | Fastest path to the real churn reasons | none | S | founder
- [ ] P1 | Set a sustainable solo iteration cadence + monthly roadmap-vs-actual review | 4-month gap in history signals drift risk | commit history | S | founder
- [ ] P2 | Track meta-weight divergence from defaults per user (proxy for accumulated model value / switching cost) | Makes the "1-year moat" measurable | `meta_weights` table | M | eng
- [ ] P2 | Pre-write the cold-start contingency plan (above) so a weak week-1 doesn't stall the project | Removes decision paralysis under bad early data | this artifact | S | founder

## Top 5 if you only do 5 things

1. Instrument D1/D7/D30 cohort retention + the cold-start funnel.
2. Track suggestion-driven-read rate — the one number that says the flywheel turns.
3. Build the ranking-eval harness and review it weekly during days 30–60.
4. Monitor scraper health and budget recurring maintenance time.
5. Interview churned users and hold a sustainable monthly roadmap review.

**Revisit trigger:** re-run at day 30 and day 90 post-launch against the real cohort curves.
