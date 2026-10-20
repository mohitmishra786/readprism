# Media & Screenshots — capture guide

*The README is the best-indexed, most-shared asset and currently has no visuals
(audit 11-2). This is the shot list; capture into `docs/media/` and reference
from the README + a 60–90s demo for launch channels (audit 12-5).*

## Set up a realistic demo account

A seed script builds a fully-enriched demo account (interest graph, summaries,
embeddings, ranked digest) end-to-end:

```bash
docker compose up -d
docker compose exec backend python scripts/seed_demo.py
```

Then log in as the demo account and enable your OS dark mode for a second set of
shots.

## Shot list (screenshots)

Captured in 1280x800 light and dark mode in `docs/media/`:

1. **Daily digest** (`/digest`) — sectioned lead/creator/deep-reads/discovery,
   showing the PRS score chips. The hero image.
   - Light: [`docs/media/digest-light.png`](media/digest-light.png)
   - Dark: [`docs/media/digest-dark.png`](media/digest-dark.png)
2. **Why-ranked tooltip** — open a card's "Why this?" showing the signal
   contributions and the "connects your interest in X and Y" line.
   - Light: [`docs/media/why-ranked-light.png`](media/why-ranked-light.png)
   - Dark: [`docs/media/why-ranked-dark.png`](media/why-ranked-dark.png)
3. **Interest graph** (`/interests`) — the interactive SVG interest map + tag cloud.
   - Light: [`docs/media/interest-graph-light.png`](media/interest-graph-light.png)
   - Dark: [`docs/media/interest-graph-dark.png`](media/interest-graph-dark.png)
4. **In-app reader** (`/read/[id]`) — editorial typography + reading telemetry progress.
   - Light: [`docs/media/reader-light.png`](media/reader-light.png)
   - Dark: [`docs/media/reader-dark.png`](media/reader-dark.png)
5. **Source management** (`/sources`) — followed feeds with trust scores and health indicators.
   - Light: [`docs/media/sources-light.png`](media/sources-light.png)
   - Dark: [`docs/media/sources-dark.png`](media/sources-dark.png)

## Demo GIF / video (60–90s, audit 12-5)

Storyboard: onboarding (interests + sample ratings) → first digest →
open a card → "Why this?" → interest graph. Keep it under 90s, no audio needed.

## Optimization

- Alt text on every image (accessibility + SEO).
- Self-host images under `docs/media/` (don't hotlink third-party CDNs).
- Prefer WebP/optimized PNG; keep the hero < 300 KB for README load.
