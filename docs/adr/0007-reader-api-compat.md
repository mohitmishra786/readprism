# ADR 0007 — Reader-API compatibility façade vs sidecar mode (EC-07)

Date: 2026-10-02 · Status: **PROPOSED — owner decision required** · Task: EC-07

## Context

ReadPrism's value is the ranking; the ecosystem around RSS readers expects
compatibility APIs. Two directions were named:

**(a) Google-Reader/Fever-compatible API façade** — expose
`/reader/api/0/...` (Google Reader) and `/fever/api` (Fever, used by Reeder,
Feed Me, Unread…) returning ReadPrism's *ranked* order and read state.

**(b) Sidecar mode** — import subscriptions + read state from an existing
Miniflux/FreshRSS instance and run ReadPrism as the ranking brain beside it.

## Option A — compatibility façade

- Effort: **M** (2–3 weeks). Both protocols are small REST surfaces;
  token auth maps to EC-03 API tokens; read state maps to interactions.
- Benefit: every Reader-compatible mobile client (Reeder, NetNewsWire via
  Fever, ReadKit) becomes a ReadPrism front-end with ranked order.
- Risks: clients expect strict Reader semantics (streams, continuations,
  edit tags); ranked order confuses clients that assume reverse-chronology;
  protocol quirks need per-client testing; we own the compatibility surface
  forever.

## Option B — sidecar import from Miniflux/FreshRSS

- Effort: **S–M** (1–2 weeks). OPML already exists (IN-13); read-state
  import needs one sync job against the instance's API + per-user API keys.
- Benefit: zero new surface for existing users — they keep their reader,
  ReadPrism becomes the digest/learning layer. Lowest friction to adoption.
- Risks: no client lock-in benefit; ongoing sync drift (read state, stars)
  needs reconciliation; the reader UI keeps chronological habits, so the
  ranked digest is additive rather than primary.

## Recommendation

**B first, A on demand.** Sidecar mode is smaller, reversible, and directly
feeds the learning loop with existing behavior; the façade is a bigger,
permanent compatibility promise that only pays off if mobile clients are a
real pull. Revisit A when users ask for it by name (Reeder is the usual
driver).

## Decision

Awaiting the owner. No implementation until approved (per EC-07 gate).
