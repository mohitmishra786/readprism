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

1. **Daily digest** (`/digest`) — sectioned lead/creator/deep-reads/discovery, showing PRS score chips.
   - Light: [`media/digest-light.png`](media/digest-light.png)
   - Dark: [`media/digest-dark.png`](media/digest-dark.png)
2. **Why-ranked explanation** — card "Why this?" panel showing signal contributions and score breakdown.
   - Light: [`media/why-this-light.png`](media/why-this-light.png)
   - Dark: [`media/why-this-dark.png`](media/why-this-dark.png)
3. **Interest graph** (`/interests`) — interactive SVG interest map with learned topic nodes and weights.
   - Light: [`media/interests-light.png`](media/interests-light.png)
   - Dark: [`media/interests-dark.png`](media/interests-dark.png)
4. **In-app reader** (`/read/[id]`) — editorial typography, standfirst summary, and reading surface theme controls.
   - Light: [`media/reader-light.png`](media/reader-light.png)
   - Dark: [`media/reader-dark.png`](media/reader-dark.png)
5. **Source management** (`/sources`) — followed feeds with trust scores and health indicators.
   - Light: [`media/sources-light.png`](media/sources-light.png)
   - Dark: [`media/sources-dark.png`](media/sources-dark.png)

## Refreshing the screenshots

To refresh all 10 screenshots:

1. Start the stack and seed the demo account:
   ```bash
   make env                      # only if .env doesn't exist yet
   docker compose up -d --build  # or `make up-lite` to use published images
   docker compose exec backend python scripts/seed_demo.py
   ```
   Note the demo email and password printed by the seed script. Wait until `curl -fsS http://localhost:3000/login` and `curl -fsS http://localhost:8000/health` both succeed.

2. Run the Playwright capture script:
   ```bash
   cd frontend && DEMO_EMAIL="<email>" DEMO_PASSWORD="<password>" BASE_URL="http://localhost:3000" npx tsx scripts/capture-screenshots.ts
   ```
   (Run `npx playwright install chromium` first if Chromium is not installed).

## Demo GIF / video (60–90s, audit 12-5)

Storyboard: onboarding (interests + sample ratings) → first digest →
open a card → "Why this?" → interest graph. Keep it under 90s, no audio needed.

## Optimization

- Alt text on every image (accessibility + SEO).
- Self-host images under `docs/media/` (don't hotlink third-party CDNs).
- Prefer WebP/optimized PNG; keep the hero < 300 KB for README load.
