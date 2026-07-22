# 08 — Legal & Compliance Audit

*Evidence: code review + web search on 2026 scraping/copyright/email law. **Not legal advice — consult counsel before hosted launch.***

## Status Snapshot

- **License mismatch across the repo**: `LICENSE` file is **MIT**; `docs/LAUNCH.md` tells the world the project is **AGPL**. These are very different commitments and one of them is being published to launch audiences. Must reconcile before any launch post.
- Scraping posture is more responsible than most: `_check_robots` honors robots.txt (but fails *open* on error). Custom `ReadPrism/1.0 (+bot url)` UA is present — alongside rotating browser-impersonation UAs, which cuts the other way (see below).
- **Copyright exposure is real**: the system stores `full_text` of scraped articles and full newsletter bodies, generates LLM summaries, and emails them. Storing/ः redistributing full third-party content is the highest-liability behavior in the product.
- No privacy policy, no ToS, no cookie/consent handling, no data-retention policy in the repo.
- Email compliance: digests are arguably transactional (user-requested) but include third-party content and a preferences link (hard-coded to `localhost:3000` in the template) — no List-Unsubscribe header, no physical-address footer.

## Findings

**License (P0).** MIT lets anyone (including a funded competitor) take the ranking engine, close it, and offer a hosted product with zero reciprocity. Given the spec's stated open-core/hosted monetization intent, **AGPL-3.0 (+ CLA) is the defensible choice** — it forces network-use competitors to open their modifications, which is exactly the compliance-as-monetization lever ([AGPL vs MIT for SaaS](https://www.getmonetizely.com/articles/should-you-license-your-open-source-saas-under-agpl-or-mit-a-decision-guide-for-founders)). Relicensing later is expensive and needs a CLA *from the first outside contributor* ([OSS licensing lessons](https://ossalt.com/guides/oss-licensing-guide-mit-apache-agpl-2026)). Right now there are effectively no outside contributors (only Dependabot) — **this is the cheapest it will ever be to switch.** Decide now.

**Scraping legality (P1).** 2026 case law is nuanced ([web-scraping legality 2026](https://use-apify.com/docs/what-is-apify/is-apify-legal)):
- *hiQ v. LinkedIn*: public scraping ≠ CFAA violation, but accepted ToS are enforceable (contract claim).
- *Reddit v. Perplexity* (pending, filed Oct 2025) and the 2026 DMCA §1201 wave target **circumventing anti-bot/rate-limit measures** — regardless of data publicness.
- **Direct implication for ReadPrism:** the rotating *browser-impersonation* User-Agents + Playwright fallback specifically to defeat 403/429 bot blocks is the behavior now under legal fire. Honoring robots.txt helps; spoofing UAs to bypass blocks hurts. **Pick a lane:** identify honestly as a feed-fetching bot and back off on blocks, or accept §1201-style risk. For a self-hostable tool the risk shifts to the *self-hoster*, but the hosted service carries it directly.
- EDPB now treats robots.txt/login-walls as signals in the GDPR legitimate-interest test — fail-open robots handling is a weak posture.

**Copyright (P1).** Storing full article text + full newsletter bodies indefinitely, then redistributing summaries by email, is more exposed than fetch-and-display. Mitigations: store only what's needed (summary + short excerpt + link), set retention limits on `full_text`, keep summaries clearly derivative + attributed with source links (the digest does link — good), and honor DSM/TDM opt-outs (EU AI Act GPAI obligations start Aug 2, 2026 — mostly relevant if training models, but the opt-out norm is spreading).

**Email (P2).** Digest is user-requested (transactional-leaning), but best practice + CAN-SPAM/GDPR: include a working unsubscribe / preferences link (currently hard-coded `http://localhost:3000/preferences` — broken in prod), a real sender identity, and List-Unsubscribe header. Use a sending subdomain + SPF/DKIM/DMARC ([Resend deliverability](https://resend.com/blog/top-10-email-deliverability-tips)).

**Newsletter forwarding (P2, ties to artifact 06).** Receiving users' forwarded newsletters means processing content the *sender's* publisher owns, on your infra — plus the abuse vector. Terms should disclaim and users should confirm they may forward.

**Third-party ToS (P2).** Groq, Resend, sentence-transformers (Apache-2.0, fine), Meilisearch (MIT, fine), pgvector (PostgreSQL license, fine). Groq/Resend ToS prohibit certain content classes and cold email — the digest use is compliant; document it.

## Checklist

- [ ] P0 | Decide MIT vs AGPL now; reconcile LICENSE and LAUNCH.md; add a CLA before accepting any human PR | Contradiction is public-facing; relicensing gets impossible once contributors join | LICENSE (MIT) vs docs/LAUNCH.md ("AGPL") | S | founder
- [ ] P1 | Choose a scraping posture: honest bot UA + back-off on blocks, OR document the risk you're accepting | 2026 §1201 suits target anti-bot circumvention specifically | `scraper.py` UA rotation + Playwright | M | founder+eng
- [ ] P1 | Add data-retention limits on stored `full_text`; keep excerpt+link, not indefinite full copies | Copyright exposure scales with what you store | `models/content.py::full_text` | M | eng
- [ ] P1 | Write Privacy Policy + ToS (telemetry, retention, shared-content model, scraping disclaimer) | Legal baseline; also required by app stores / Google sign-in later | none in repo | M | founder
- [ ] P1 | Fix the digest preferences/unsubscribe link (hard-coded localhost) + add List-Unsubscribe + real footer | Broken unsubscribe = spam complaints + CAN-SPAM issue | `templates/digest_email.html` | S | eng
- [ ] P2 | Make robots.txt handling fail-closed (or configurable) and cache robots results | Fail-open is a weak GDPR/good-faith posture | `scraper.py::_check_robots` | S | eng
- [ ] P2 | Add a "you confirm you may forward this" gate + abuse handling to newsletter intake | Publisher-content + abuse liability | `api/newsletter.py` | S | eng
- [ ] P2 | Document third-party ToS compliance (Groq/Resend content + no-cold-email) in docs | Cheap insurance | none | S | founder

## Top 5 if you only do 5 things

1. Resolve the MIT-vs-AGPL contradiction this week and add a CLA — it's free now, costly later.
2. Pick and document a scraping posture that accounts for 2026 §1201 anti-circumvention suits.
3. Cap what you store: excerpt + link, not indefinite full article/newsletter text.
4. Publish a real Privacy Policy + ToS before the first hosted signup.
5. Fix the broken unsubscribe/preferences link and add List-Unsubscribe.

**Revisit trigger:** re-run before hosted launch, on first outside contributor, and if you begin training/fine-tuning any model on stored content.
