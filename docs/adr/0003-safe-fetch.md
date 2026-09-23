# ADR 0003 — safe_fetch is the user-URL client

- **Status:** Accepted
- **Date:** 2026-09-24
- **Context tags:** ssrf, ingestion

## Context

`validate_public_url` existed, but `feedparser.parse(url)` fetched the feed
itself, which skipped the check. Several callers also built their own
`httpx.AsyncClient`. Decision D-08 and task P0-06 require one outbound path
for user-supplied URLs.

## Options

1. Keep per-caller clients and remember to validate first. A new caller will
   forget, and feedparser's own fetch already did.
2. One `safe_fetch()` that checks the scheme, rejects credentials, resolves
   DNS and blocks non-global addresses on every redirect, caps the body, and
   applies a timeout. Parse feeds from the bytes it returns.

## Decision

Option 2. `safe_get` is a wrapper around `safe_fetch`. Browserless is the
remaining exception: the URL is validated before `page.goto`, and a route
hook aborts any request whose URL fails the same check. Browserless still
resolves DNS itself, so a rebinding between the check and the browser's
connect is possible. Operator-configured hosts (Meilisearch, Notion,
Readwise, the iTunes Search API host, the Browserless CDP endpoint) are not
user URLs and keep their own clients. A feed URL returned by iTunes is
validated before it is stored.

## Consequences

- Tests inject a resolver and an `httpx` transport. They do not use the network.
- A self-hoster who must scrape a LAN feed sets `SSRF_PROTECTION_ENABLED=false`
  and accepts that trade-off on a single-tenant box.
- IP pinning (connect to the resolved address with the original Host header)
  is not implemented. HTTPS certificate checks make a naive pin break
  legitimate feeds. The mixed-answer case is rejected at resolve time.
