# 11 — SEO & Discoverability Audit

*Evidence: repo (Next 16 app), GitHub metadata, web search on category SERPs (July 2026).*

## Status Snapshot

- **GitHub discoverability is near-zero and trivially fixable**: repo has **no topics/tags**, `description` is null, homepage is null, Discussions off, 1 star. These are the cheapest wins available and none are done.
- **No marketing site / SEO surface exists.** There is a single app landing page (`app/page.tsx`) — a JS-heavy, `"use client"` cursor-spotlight hero that immediately redirects authenticated users to `/digest`. It has minimal indexable text, no comparison pages, no blog, no sitemap, no `robots.txt`.
- Root-layout metadata exists (title/description/OG-ish) — decent baseline — but the page content is client-rendered canvas, so there's little crawlable copy and LCP is at risk from remote hero images + canvas work.
- **Competitors own the category SERP.** Nearly every 2026 pricing/comparison search returns **Readless.app** blog pages ("Feedly vs Inoreader vs NewsBlur 2026," "X pricing 2026," etc.). Readless is running an aggressive programmatic-SEO comparison-content machine and is eating the exact keywords ReadPrism needs.
- The keyword space is winnable on long-tail/self-host terms but not on head terms ("RSS reader") without content investment.

## Findings

**GitHub (the primary near-term channel for ICP #1).**
- Add topics: `rss-reader`, `self-hosted`, `content-aggregation`, `personalization`, `machine-learning`, `fastapi`, `nextjs`, `pgvector`, `recommendation-engine`, `newsletter`.
- Set `description` + `homepage`. Turn on Discussions (support + SEO). A strong README already exists (14KB, good) — it's the best-indexed asset; add screenshots/GIF of the ranking + interest graph.
- 1 star, 0 forks, no external contributors → a Show HN is the discovery event; the repo must be launch-polished first (dead code, doc drift — see artifact 04).

**Marketing-site SEO (needed before/around launch).**
- No `sitemap.xml`, no `robots.txt`, no per-route metadata beyond root, no OpenGraph image, no structured data.
- The landing is client-only canvas → poor crawlability + LCP. For SEO you need a *static, text-rich* marketing route (can coexist with the app under a marketing path or separate site).
- Content strategy: the winnable clusters are **comparison** ("readprism vs feedly/inoreader/newsblur", "open source feedly alternative", "self-hosted RSS reader with AI ranking") and **explainer** ("how personalized content ranking works", "reading-behavior signals"). The ranking-engine transparency is unusually good blog fodder for the dev audience (also serves marketing — artifact 12).
- **Compete where Readless is thin:** self-hosting, open-source, and the *technical* how-it-works angle — Readless is a hosted SaaS content farm; it won't write a credible "here's our gradient-descent meta-weighting" post. That's ReadPrism's defensible content niche.

**Page speed targets.** Marketing pages should be static/SSG, LCP < 2.5s, hero images self-hosted + `next/image`, drop the canvas spotlight on the indexable marketing route (keep it for the app entry if desired).

## Checklist

- [ ] P0 | Set GitHub topics, description, homepage; enable Discussions | Zero-cost discoverability for the primary ICP channel; currently all empty | `gh api` shows topics=[], description=null | S | founder
- [ ] P0 | Add README screenshots/GIF of digest + why-ranked + interest graph | The README is the best-indexed, most-shared asset and has no visuals | README.md | S | founder
- [ ] P1 | Build a static, text-rich marketing route with sitemap.xml + robots.txt + per-page metadata + OG image | No crawlable SEO surface exists today | `app/page.tsx` client-only | M | founder/eng
- [ ] P1 | Ship 3–5 comparison pages (vs Feedly, Inoreader, NewsBlur, Readwise) + "open-source Feedly alternative" | Readless owns these SERPs; comparison intent converts | competitor SERP dominance (search) | M | founder
- [ ] P1 | Publish 1 flagship technical post: "How ReadPrism ranks: 8 signals + per-user gradient descent" | Dev-audience link magnet + defensible vs SaaS content farms | code is the differentiator | M | founder
- [ ] P2 | Make the marketing landing SSG with self-hosted `next/image` hero; drop canvas on indexable routes | LCP/crawlability for organic | RevealLayer canvas + remote images | M | eng
- [ ] P2 | Add structured data (SoftwareApplication) + OG/Twitter cards | Rich results + social preview | root metadata only | S | eng
- [ ] P2 | Submit to open-source directories (awesome-selfhosted, alternativeto, OSSAlt) | Durable backlinks + ICP-#1 discovery | none | S | founder

## Top 5 if you only do 5 things

1. Fill in GitHub topics/description/homepage and enable Discussions — 15 minutes, real impact.
2. Add visuals (GIF/screenshots) to the README before Show HN.
3. Stand up a static marketing route with sitemap/robots/metadata.
4. Write the 3 comparison pages Readless is currently monopolizing.
5. Publish the technical "how the ranking works" post — your one defensible SEO/marketing asset.

**Revisit trigger:** re-run 30 days after the marketing site ships, and after Show HN (measure referral + branded-search lift).
