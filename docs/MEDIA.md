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

Captured at 1280x800 in `docs/media/`. The app has one look, the landing
page's dark theme, so there is one set:

1. **Daily digest** (`/digest`): ranked sections with score chips. [`media/digest.png`](media/digest.png)
2. **Why-ranked explanation**: a card's "Why this?" panel with the signal breakdown. [`media/why-this.png`](media/why-this.png)
3. **Interest graph** (`/interests`): learned topics and weights. [`media/interests.png`](media/interests.png)
4. **In-app reader** (`/read/[id]`): summary standfirst and reading controls. [`media/reader.png`](media/reader.png)
5. **Source management** (`/sources`): followed feeds with relevance and health. [`media/sources.png`](media/sources.png)

## Refreshing the screenshots

To refresh all 5 screenshots:

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
