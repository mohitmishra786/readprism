# Security model

This is the control list for a self-hosted ReadPrism. It describes what the
code does today. `SECURITY.md` at the repo root is the vulnerability-reporting
policy.

## Outbound fetches

User-supplied URLs (feeds, scrape targets, creator pages, robots.txt, feed
autodiscovery, iTunes feed URLs before they are stored) go through
`app.utils.ssrf.safe_fetch`.

- Schemes: `http` and `https` only.
- Userinfo in the URL is rejected.
- The host is resolved and every address must be globally routable. Loopback,
  private, link-local (including `169.254.169.254`), multicast, unspecified,
  and non-global ranges (including `100.64.0.0/10`) are rejected. The same
  check runs on every redirect.
- Decimal and hex IPv4 literals are checked as IPs.
- Body size and timeout are capped (`DEFAULT_MAX_BYTES` is 5 MB; feeds use 2 MB).
- `SSRF_PROTECTION_ENABLED=false` turns the check off for a single-tenant
  homelab that must read a LAN feed.

Not user URLs, and therefore not on this path: Meilisearch, Notion, Readwise,
the iTunes Search API host, and the Browserless CDP endpoint. Those hosts come
from operator configuration.

Browserless still performs its own DNS. Before `page.goto`, the target is
validated, and a route hook aborts any request that fails `validate_public_url`.
A DNS rebind between that check and the browser's connect is a residual risk
(ADR 0003).

## HTML

Ingested HTML is allowlisted with `nh3` (`app.utils.sanitize`). Links receive
`rel="noopener noreferrer"`. The reader runs DOMPurify again and the `/read`
routes send a Content-Security-Policy that blocks object embeds and
frame-ancestors. Digest email is rendered with Jinja autoescape; the plain
fallback uses `html.escape`.

## XML

Feeds and OPML are rejected when they contain a DOCTYPE or an entity
declaration, when they exceed `XML_MAX_BYTES`, or (OPML) when they contain more
than `OPML_MAX_OUTLINES` outlines. OPML is also parsed with defusedxml before
listparser sees it.

## Auth and config

- Passwords are bcrypt hashes.
- Access tokens are short-lived; refresh tokens rotate and the previous token
  is revoked (`tests/test_api/test_auth.py`).
- Login, registration, magic-link, and feedback posts are rate-limited per IP.
  The limiter fails open if Redis is down.
- Outside `APP_ENV=development`, startup refuses the default `SECRET_KEY` and
  any key shorter than 32 characters.
- CORS allows `FRONTEND_URL` plus `CORS_EXTRA_ORIGINS`. Development also allows
  `http://localhost:3000` and `http://localhost:3001`.
- Newsletter inbound webhooks require a Mailgun HMAC and reject stale
  timestamps. With no signing key, non-development boots fail closed.

## What leaves the machine

See `docs/THIRD_PARTY_SERVICES.md` and `docs/PRIVACY.md`. With no LLM key, no
SMTP password, and no Sentry DSN, ingestion and ranking stay on the box. There
is no product telemetry SDK.
