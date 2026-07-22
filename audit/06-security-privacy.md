# 06 — Security & Privacy Audit

*Evidence: code review + dependency inspection + web search on data law (July 2026).*

## Status Snapshot

- Baseline hygiene is decent: bcrypt password hashing, JWT HS256, `.env` gitignored, `.env.example` uses placeholders, CodeQL + Dependabot green, secrets read via pydantic-settings.
- **Highest risk: the newsletter inbound webhook (`/newsletter/inbound`) has no authentication and no signature verification** — anyone can POST arbitrary content attributed to any user by guessing the `user-{uuid}@` recipient format. Spam/phishing/content-injection vector directly into ranking + digests.
- **No account-deletion or data-export-for-erasure path exists** — a hard GDPR/CCPA gap for a behavioral-tracking product that stores reading history.
- JWT has no revocation/refresh-token model (the "refresh" endpoint re-issues from any still-valid token; logout is client-side cookie delete only). Token lifetime 24h.
- No rate limiting on auth endpoints (only a per-user digest-generation throttle exists). Credential-stuffing and registration-spam are open.

## Findings (ranked)

**P0 — Unauthenticated newsletter webhook.** `api/newsletter.py::inbound_email` accepts form/JSON with `sender`, `subject`, `body`, `recipient`, derives `user_id` from the local part, and ingests. No Mailgun signature check (`timestamp`/`token`/`signature` HMAC), no shared secret, no sender allow-listing. Anyone who learns a user's inbox address (or brute-forces UUIDs) injects content into that user's ranking pipeline and digest email. Also a stored-XSS/phishing surface if body HTML reaches the reader unsanitized.

**P0 — No user data deletion / export.** Product stores email, reading telemetry, interest graph, interactions. Grep finds no `delete account` / erasure / export-my-data endpoint (`integrations/export.py` is OPML/content export, not a GDPR subject-access bundle). Required for EU/California users on both self-hosted and hosted. ([EDPB scraping/data guidance](https://www.reedsmith.com/our-insights/blogs/technology-law-dispatch/102nbqu/edpb-web-scraping-guidelines-for-ai-making-the-impossible-possible/))

**P1 — Auth hardening.**
- No rate limiting on `/auth/login` `/auth/register` → credential stuffing, user enumeration (register returns 409 "Email already registered" — confirms account existence).
- Refresh model is weak: `/auth/refresh` accepts any non-expired access token as a "refresh_token" and mints a new one; no separate refresh secret, no rotation, no revocation list. A leaked token is valid 24h with no kill switch.
- JWT cookie is set client-side via js-cookie with `sameSite: strict` but **not `httpOnly`** (can't be, it's JS-set) → XSS can exfiltrate the token. Consider httpOnly server-set cookies.
- CORS `allow_credentials=True` with an explicit origin list is fine, but `allow_methods/headers=["*"]` with credentials is broad.

**P1 — Content/PII sharing across tenants.** `content_items.url` is globally unique and content rows are shared across users (good for cost). Means one user's *scraped/newsletter* content (which can contain personal or paywalled material) is stored in a shared table keyed only by URL — a newsletter forwarded by user A and user B dedupes to one row. Generally fine for public web content; risky for newsletter bodies (often personalized, may contain the recipient's name/unsubscribe tokens). Segregate newsletter-sourced content per user.

**P2 — Secrets & defaults.** `secret_key` defaults to `"change_me..."`; app boots with it (only LLM absence warns). Add a startup hard-fail when `app_env != development` and secret is default. `.env.example` ships a real-looking `admin@mohitmishra7.com` sender and a default `MEILISEARCH_MASTER_KEY=readprism_search_key` — document that these must be changed.

**P2 — Scraping/Playwright sandboxing.** Browserless runs as a separate container (good isolation). `_check_robots` fails-open (allows on error) — a compliance choice to revisit (artifact 08). SSRF: `scrape_page`/source-add fetches arbitrary user-supplied URLs server-side with no allow-list or internal-IP block → an attacker adds `http://169.254.169.254/…` or internal hosts as a "source." **Raise this to P1 for any hosted deployment.**

**Dependencies.** Pins are current and CI is green (Dependabot active, 4-update PRs landing weekly). `psycopg2-binary` + `asyncpg` both present (sync path for Alembic). No known-CVE pins spotted at these versions, but the Dockerfile uses `python:3.14-slim` while CI/README target 3.11 — version drift worth reconciling.

## Checklist

- [ ] P0 | Add Mailgun HMAC signature verification (+ shared secret) to `/newsletter/inbound`; reject unsigned posts | Open injection into ranking + user digest email | `api/newsletter.py` | S | eng
- [ ] P0 | Add SSRF protection to all server-side URL fetches (block private/link-local IPs, allow-list schemes) | User-supplied source URLs fetched server-side = cloud-metadata theft on hosted | `ingestion/scraper.py`, source-add flow | M | eng
- [ ] P0 | Implement account deletion + data export (erasure) endpoints | GDPR/CCPA blocker for launch in EU/CA | none exists | M | eng
- [ ] P1 | Rate-limit auth endpoints; make register/login non-enumerating | Credential stuffing + user enumeration open | `api/auth.py` | S | eng
- [ ] P1 | Real refresh-token model (separate secret, rotation, revocation) or short-lived access + server httpOnly cookie | Leaked token unrevocable for 24h | `api/auth.py::refresh` | M | eng
- [ ] P1 | Segregate newsletter-sourced content per user (don't dedupe personalized email bodies into shared rows) | Cross-tenant leakage of personalized newsletter content | `models/content.py` unique url | M | eng
- [ ] P1 | Sanitize/escape scraped & newsletter HTML before it reaches the reader/digest | Stored XSS / phishing via ingested content | reader page, `digest_email.html` | M | eng
- [ ] P2 | Hard-fail startup on default `secret_key` outside development | Silent insecure deploys | `config.py` | S | eng
- [ ] P2 | Reconcile Python 3.14 (Dockerfile) vs 3.11 (CI/README) | Build/runtime drift | backend/Dockerfile | S | eng
- [ ] P2 | Publish a privacy policy describing telemetry, retention, and the shared-content model | Trust + legal baseline (artifact 08) | none | S | founder

## Top 5 if you only do 5 things

1. Authenticate the newsletter webhook (signature verify) — it's an open door today.
2. Add SSRF guards to server-side URL fetching before any hosted deploy.
3. Ship account deletion + data export.
4. Rate-limit and de-enumerate auth.
5. Sanitize ingested HTML on the reader/email path.

**Revisit trigger:** re-run before hosted launch and after any auth/ingestion refactor; mandatory security-review pass before first public signup.
