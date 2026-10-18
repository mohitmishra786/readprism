# 15 — Launch Checklist

*Launch-day mechanics. Assumes artifact 14's pre-launch blockers are cleared. Evidence: repo + LAUNCH.md + infra reality (July 2026).*

## Status Snapshot

- Launch copy is ready (`docs/LAUNCH.md` — HN + r/rss + r/selfhosted), honest and technical in the register HN rewards. Fix the placeholder repo URL + license claim first.
- The realistic launch is a **Show HN + r/selfhosted/r/rss self-host launch**, not a Product Hunt consumer launch (wrong audience for a self-hostable dev tool). PH comes later with a hosted product.
- Biggest launch-day risk: a **traffic spike hitting either (a) the single hosted demo instance on a solo-pool worker, or (b) the ingestion pipeline** — neither is load-tested. Second risk: being unavailable to answer HN comments (single founder).
- No support channel, no metrics dashboard, no rollback plan currently exist.

## Checklist

**Sequencing**
- [ ] P0 | Pick one primary launch (Show HN) on a Tue–Thu, ~8–10am ET; don't multi-launch same day | Splitting attention across channels solo = present nowhere | LAUNCH.md channels | S | founder
- [ ] P1 | Stagger: Show HN day 1 → r/selfhosted + r/rss day 2–3 → Lobsters → directories | Sustains a discovery tail instead of one spike | LAUNCH.md has copy for each | S | founder
- [ ] P2 | Hold Product Hunt until a hosted product exists | PH audience ≠ self-host audience | artifact 12 | S | founder

**Load & reliability (launch-day survival)**
- [ ] P0 | Load-test the hosted demo + ingestion at 10–50× baseline before launch morning | Solo-pool worker + demo instance are the fragile points | artifact 07 | M | eng
- [ ] P0 | Rate-limit signups + demo actions; sandbox the demo account (read-only or reset-on-schedule) | A shared demo gets abused/spammed within hours | no rate limiting on auth (artifact 06) | M | eng
- [ ] P0 | Have a rollback plan: pinned last-good image/tag + one-command revert + status note | Launch-day regressions need a 5-minute undo | CI builds images; no documented rollback | S | eng
- [ ] P1 | Scale plan for the demo: pre-provision headroom (bigger host / extra worker containers per queue) for 48h | Solo pool will choke; temporary over-provision is cheapest insurance | compose worker | M | eng
- [ ] P1 | Confirm email won't hit Resend's 100/day free cap during a signup spike (or pre-upgrade to Pro) | Digest delivery silently fails past the cap | artifact 07/13 | S | eng

**Support & presence**
- [ ] P0 | Staff a support channel (GitHub Discussions + a monitored email); be present in HN thread all day | HN rewards responsive founders; silence kills momentum | Discussions currently off | S | founder
- [ ] P1 | Prewrite FAQ answers (cold start, NewsBlur diff, self-host steps, privacy, license) | You'll get the same 5 questions; canned honest answers save the day | LAUNCH.md drafts some | S | founder

**Metrics (dashboard ready BEFORE traffic)**
- [ ] P0 | Live day-1 dashboard: signups, onboarding completion, first-digest opens, errors (Sentry), infra health | Flying blind during the one traffic event you get | no analytics/monitoring yet | M | eng
- [ ] P1 | Track referral sources + GitHub stars/clones velocity | Know which channel actually worked | GitHub insights + analytics | S | founder

**Press kit basics**
- [ ] P1 | Demo GIF/video, screenshots, one-paragraph + one-line descriptions, logo | Every repost needs assets; you have none | no media in repo | M | founder
- [ ] P2 | A short "how it works" diagram (the ranking pipeline) | Shareable, on-brand, explains the wedge fast | README has ASCII arch only | S | founder

## Top 5 if you only do 5 things

1. Load-test the demo + ingestion, and rate-limit/sandbox the demo before launch morning.
2. One primary launch (Show HN), founder present in-thread all day.
3. Day-1 dashboard (signups → onboarding → first-digest-open → errors) live before you post.
4. Rollback plan + pre-provisioned headroom + email cap pre-check.
5. Support channel on (Discussions) + prewritten FAQ answers.

**Revisit trigger:** re-run the day before launch; re-run again before any second (hosted / Product Hunt) launch.
