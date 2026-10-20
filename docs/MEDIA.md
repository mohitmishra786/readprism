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

1. **Daily digest** (`/digest`) — sectioned lead/creator/deep-reads/discovery,
   showing the PRS score chips. The hero image.
2. **Why-ranked tooltip** — open a card's "Why this?" showing the signal
   contributions and the "connects your interest in X and Y" line.
3. **Interest graph** (`/preferences`) — the SVG graph + tag cloud ("watch it
   learn").
4. **In-app reader** (`/read/[id]`) — editorial typography + scroll progress.
5. **Source health** (`/sources`) — a source with a "Fetch issues" badge.

## Demo GIF / video (60–90s, audit 12-5)

Storyboard: onboarding (interests + sample ratings) → first digest →
open a card → "Why this?" → interest graph. Keep it under 90s, no audio needed.

## Optimization

- Alt text on every image (accessibility + SEO).
- Self-host images under `docs/media/` (don't hotlink third-party CDNs).
- Prefer WebP/optimized PNG; keep the hero < 300 KB for README load.
