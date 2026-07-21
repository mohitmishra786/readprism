# ReadPrism Privacy Policy

*Last updated: 2026-07-21. This is a baseline policy template for the ReadPrism
software; it is not legal advice. Operators of a hosted ReadPrism instance should
have it reviewed by counsel and adapt it to their jurisdiction before collecting
user data.*

ReadPrism is a personalized reading tool. To rank content for you, it processes
data about what you read and how you read it. This document explains what is
collected, why, how long it is kept, and the controls you have.

## Who is the data controller

For a **self-hosted** instance, the operator who runs it is the data controller.
For any **hosted** ReadPrism service, the entity offering that service is the
controller. This template refers to whoever runs the instance as "we".

## What we collect

- **Account data:** email address, a bcrypt password hash, display name, and
  your preferences (digest frequency, digest time, timezone, serendipity level,
  tier).
- **Content you add:** the sources, creators, and OPML feeds you subscribe to,
  and newsletters you forward to your ReadPrism inbox address.
- **Reading telemetry:** for items you open in the in-app reader, we record
  scroll depth, active reading time, whether you reached the end, re-reads,
  completion percentage, saves, shares, skips, and explicit ratings/feedback.
  This is the behavioural signal that powers ranking.
- **Derived data:** an interest graph (topics + weights), per-source and
  per-creator trust weights, learned ranking meta-weights, and content
  embeddings.

We do **not** sell personal data, and we do not use it for advertising.

## Why we process it (legal bases)

- To provide the service you asked for (ranking, digests) — performance of a
  contract.
- To improve ranking quality for you — legitimate interest, balanced against
  your rights; you can turn telemetry-driven features off by not using the
  in-app reader.

## Retention

- **Reading telemetry and derived data** persist while your account exists so
  the model can keep learning.
- **Full article text** we fetch is pruned to a short excerpt after
  `CONTENT_FULL_TEXT_RETENTION_DAYS` (default 90 days); we keep the summary,
  excerpt, and link, not an indefinite full copy.
- When you delete your account, all your personal data is erased (see below).

## Shared content model

Public web/RSS content is deduplicated across users and stored once, keyed by
URL, with no owner — this keeps costs and summarization efficient. Content that
is personal to you — **forwarded newsletters** — is tagged with your user id, is
never shown to other users, and is only readable by you.

## Third-party processors

ReadPrism can send data to the third-party services below when configured. See
[THIRD_PARTY_SERVICES.md](THIRD_PARTY_SERVICES.md) for details.

- **Groq** (and optionally OpenAI): article text/titles are sent to generate
  summaries. Summaries are cached.
- **Email provider (Zoho SMTP / Resend):** your email address and digest content
  to deliver digests.
- **Meilisearch, Postgres, Redis, Browserless:** run within the operator's own
  infrastructure.

Self-hosters may supply their own API keys, in which case those providers'
terms apply to the operator.

## Your rights and controls

- **Access / export:** `GET /api/v1/account/export` returns a portable JSON copy
  of your data (GDPR Art. 20 / CCPA).
- **Erasure:** `DELETE /api/v1/account` permanently deletes your account and all
  associated personal data (GDPR Art. 17).
- **Unsubscribe:** every digest email has a one-click unsubscribe link; you can
  also set digest frequency to in-app-only in preferences.
- **Topic controls:** you can suppress topics and adjust interests in the app.

EU/California residents additionally have the rights to rectification,
restriction, objection, and to lodge a complaint with a supervisory authority.

## Security

Passwords are hashed with bcrypt. The API authenticates the newsletter webhook,
guards server-side fetches against SSRF, sanitizes ingested HTML, and rate-limits
authentication. See [SECURITY.md](../SECURITY.md) to report a vulnerability.

## Changes

Material changes to this policy will be reflected here with an updated date.
