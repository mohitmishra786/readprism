# Roadmap

<p class="lead">Where Weirling is going, in four milestones. Live status, with
every issue, is on the <a href="https://github.com/mohitmishra786/weirling/milestones">GitHub
milestones</a> page.</p>

```mermaid
flowchart LR
    accTitle: Weirling milestones
    accDescr: Four milestones in order, from core fixes to a hosted beta, the public launch, and year one.

    m0["M0: Core loop"] --> m1["M1: Hosted beta"]
    m1 --> m2["M2: Public launch"]
    m2 --> m3["M3: Year one"]
```

## M0: Core loop fixes

Make the daily loop trustworthy: ingest, rank, deliver, learn.

- All P0 fixes from the October 2026 audit
- Docs that match the code
- Clear notices for platforms that stopped offering feeds (Reddit)
- A dogfooding instance running every day

## M1: Hosted beta

Run Weirling for a small group of readers.

- **Shared feeds:** a feed followed by many readers is fetched once
- **One ranker** with faithful explanations and pairwise learning
- Onboarding that produces a useful first digest
- A concierge beta with hands-on support

## M2: Public launch

Everything needed to open the hosted service and make self-hosting easy.

- **Billing and plans:** Reader and Pro, a 30-day trial, quotas and trial emails
- **Self-hosting:** the all-in-one image, a first-boot setup screen, backups
  and an upgrade guide
- **Operations:** metrics, dashboards and alerts
- **Trust:** hosted terms and privacy, account deletion that cancels billing,
  and an external security review

## M3: Year one

Grow the product once the launch is stable.

- A heavier Pro tier: more feeds, story synthesis, API and MCP access
- Transcripts and summaries in more languages
- Extracting the ranker as a reusable library
- Scaling beyond the first thousand readers

## Decisions and history

- Architecture decisions: [decision records](adr/index.md)
- What changed in each version: [release notes](releases/v0.2.0.md)
- The engineering task log (detailed and long) lives in
  [`docs/PROGRESS.md`](https://github.com/mohitmishra786/weirling/blob/main/docs/PROGRESS.md)
  in the repository.
