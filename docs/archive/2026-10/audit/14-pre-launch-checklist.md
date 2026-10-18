# 14 — Pre-Launch Checklist

*Everything that should be true before any public link is shared. Evidence: repo state July 2026. "Launch" here = Show HN / public repo promotion, not a funded GA.*

## Status Snapshot

- The code is further along than a typical pre-launch project, but several **launch-blocking** gaps are non-code: license contradiction, no privacy policy/ToS, broken email links, unauthenticated webhook, no error monitoring, no backup, and no verified clean-machine install.
- There is **no deployed instance** and **no demo/sandbox account** — reviewers from HN cannot try it without self-hosting, which caps launch conversion.
- CI is green (backend/frontend/CodeQL), Dependabot active — good engineering baseline.
- The concierge cold-start validation (artifact 01) is arguably the real pre-launch gate: launching before knowing day-1 quality risks a public "it's just a random feed" verdict.

## Checklist

**Legal / trust (blocking)**
- [ ] P0 | Resolve MIT vs AGPL; make LICENSE and LAUNCH.md agree; add CLA | Public contradiction + monetization exposure | LICENSE vs LAUNCH.md | S | founder
- [ ] P0 | Publish Privacy Policy + ToS (telemetry, retention, scraping, shared content) | Legal baseline before collecting any user data | none in repo | M | founder
- [ ] P0 | Fix hard-coded `localhost:3000` preferences/unsubscribe link + add List-Unsubscribe | Broken unsubscribe = spam complaints on the one retention channel | `digest_email.html` | S | eng

**Security (blocking)**
- [ ] P0 | Authenticate the newsletter webhook (signature verify) | Open content injection into ranking + user email | `api/newsletter.py` | S | eng
- [ ] P0 | SSRF-guard server-side URL fetches; hard-fail on default SECRET_KEY | Metadata theft / insecure deploy on any hosted instance | `scraper.py`, `config.py` | M | eng
- [ ] P0 | Account deletion + data export endpoints | GDPR/CCPA + user trust | none | M | eng

**Reliability / ops (blocking for hosted; strongly advised for self-host demo)**
- [ ] P0 | Error monitoring (Sentry/GlitchTip) on backend+worker+frontend | You can't run a launch-day incident blind | none | S | eng
- [ ] P0 | Nightly pg_dump + documented restore | User behavioral history is the product | volumes only | S | eng
- [ ] P1 | Beat healthcheck/liveness + split Celery queues | Silent ingestion stall under launch traffic | compose | M | eng

**Product readiness (blocking for conversion)**
- [ ] P0 | Stand up a hosted demo / sandbox account reviewers can try without self-hosting | HN converts on "try it in 30s," not "clone and docker compose" | no deployment | M | founder/eng
- [ ] P0 | Verify clean-machine quickstart works first try (single required env var) | A broken `docker compose up` on launch day is fatal | unverified; Python 3.14/3.11 drift, image build | M | eng
- [ ] P0 | Run the concierge cold-start test; only launch if day-7 quality clears the bar | The public verdict hinges on first-run quality | artifact 01 | M | founder
- [ ] P1 | First-digest honest-state (no empty/random digest post-onboarding) | The make-or-break UX moment | artifact 10 | M | eng
- [ ] P1 | README screenshots/GIF + fix doc drift (Next 16/React 19, Zoho vs Resend) | The README is the launch artifact | README vs code | S | founder

**Instrumentation (measure the launch)**
- [ ] P0 | Product analytics for the cold-start funnel: signup→onboard→first-digest-open→day-7 return + suggestion-read rate | Launching without measuring cold start wastes the traffic spike | no analytics in repo | M | eng
- [ ] P1 | Opt-in self-host telemetry ping | Otherwise self-host launches teach you nothing | none | M | eng

**Growth prep**
- [ ] P1 | GitHub topics/description/homepage/Discussions + directory submissions | Zero-cost discoverability, currently empty | gh metadata | S | founder
- [ ] P1 | Waitlist/early-access page for the (not-yet-built) hosted product | Capture ICP-#2 demand you can't yet serve | none | S | founder
- [ ] P2 | Static marketing route + 3 comparison pages + flagship post | Organic acquisition + SERP defense vs Readless | artifacts 11/12 | M | founder

## Top 5 if you only do 5 things

1. Run the concierge cold-start test — it's the real go/no-go.
2. Close the security P0s (webhook auth, SSRF, deletion/export) and legal P0s (license, privacy/ToS).
3. Stand up a hosted demo + verify the clean-machine install.
4. Add error monitoring, backups, and cold-start analytics before traffic arrives.
5. Fix the broken email links and README drift, add GitHub topics + visuals.

**Revisit trigger:** re-run this list in full the week before any public link goes out; nothing here is "later."
