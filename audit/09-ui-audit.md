# 09 — UI Audit

*Evidence: frontend/src review (Next 16 / React 19 / Tailwind v4), July 2026.*

## Status Snapshot

- A real, themed design system exists: `globals.css` defines an "editorial magazine" system — ink/prism/spectrum color scales, Playfair/Source-Serif/Inter/JetBrains fonts, reading-width tokens (`--max-width-reading: 42rem`), section-accent gradients. This is above-average craft for a solo pre-launch app.
- The landing page is a bespoke cursor-spotlight dark hero (canvas radial-mask reveal) — visually striking but heavy (per-mousemove `canvas.toDataURL()` on every frame — a performance and battery concern).
- **The app itself has no dark mode** (`dark:` / `prefers-color-scheme` = 0 occurrences), despite the marketing hero being dark — a jarring light/dark whiplash from landing → app, and a miss for a reading app used at night.
- The in-app reader is the strongest surface: real typography, scroll progress, telemetry-instrumented. It renders article `full_text` as HTML (XSS risk — see artifact 06).
- Inline `style={{…}}` objects coexist with the Tailwind system (e.g. OnboardingWizard uses inline styles throughout) — inconsistent and will drift.

## Findings

**Information density & hierarchy — good.** ContentCard exposes PRS + top-3 signal explanations with section-accent gradients; digest is sectioned (lead/creator/deep_reads/discovery). The "why ranked" tooltip is a genuine differentiator rendered well.

**Typography for long-form — good in the reader, unfinished elsewhere.** Reader uses `.prose-reader` + serif article sizing (1.125rem/1.8). But onboarding and several app pages fall back to system-default inline styles, so the editorial system is applied unevenly.

**Dark mode — missing (P1).** For a reading product this is table-stakes in 2026; Readwise/Feedly/Inoreader all ship it. The tokens are already CSS variables, so a `prefers-color-scheme` + `.dark` variant is low-effort relative to impact.

**Mobile / responsive (P1).** App shell uses `max-w-3xl`/`max-w-5xl` with horizontal-scroll nav; no evidence of a mobile-tuned layout, bottom nav, or touch targets beyond default. Spec puts PWA in Phase 4, but the *interim mobile web* experience is what real users hit first from a Show HN link on their phone. `manifest.json` + `sw.js` exist (PWA scaffolding present) but there's no install prompt or offline strategy verified.

**Accessibility (P1).** Minimal ARIA (a couple of `aria-label`s). No skip-link, unaudited color contrast (prism-600 on white is fine; stone-500 text may fail WCAG AA), the spotlight landing page is mouse-only (no keyboard/touch reveal path, no reduced-motion honoring). `prefers-reduced-motion` not handled for the shimmer/spotlight animations.

**Landing perf (P2).** `RevealLayer` rebuilds a full-viewport canvas gradient and calls `toDataURL()` on every cursor move via RAF — expensive, GC-heavy, and does nothing on touch devices (mouse-only). Two large remote hero images from a third-party image CDN (`images.higgs.ai`) — external dependency + LCP risk.

**Consistency (P2).** Two styling paradigms (Tailwind v4 tokens vs inline styles). Email template hard-codes `localhost:3000` (artifact 08). Signal-label maps are duplicated in `ContentCard.tsx` and `delivery.py` — drift risk.

## Checklist

- [ ] P1 | Add dark mode to the app (tokens are already variables; add `.dark`/media-query variants) | Reading app at night without dark mode is a churn reason; also fixes landing→app whiplash | globals.css `@theme`; 0 `dark:` usages | M | design/eng
- [ ] P1 | Audit + fix mobile web layout (nav, touch targets, reader width) — the real first impression from mobile launch traffic | Phase-4 PWA is irrelevant if interim mobile web is broken | `(app)/layout.tsx` max-w + scroll nav | M | design/eng
- [ ] P1 | Accessibility pass: contrast (stone-500 text), skip link, `prefers-reduced-motion`, keyboard path | Basic WCAG + HN/dev audience notices | landing spotlight, globals.css | M | design/eng
- [ ] P2 | Unify styling: move OnboardingWizard + inline-styled pages onto the Tailwind system | Visual drift + maintenance | components/onboarding/* | M | eng
- [ ] P2 | Make the spotlight landing degrade gracefully (touch fallback, reduced-motion, lazy hero images, self-host images) | Mouse-only hero + heavy canvas hurts mobile LCP (artifact 11) | `app/page.tsx` RevealLayer | M | design/eng
- [ ] P2 | De-duplicate the signal-label map (share one source of truth FE/BE) | Two copies already exist | ContentCard.tsx / delivery.py | S | eng
- [ ] P2 | Sanitize reader HTML (also a security item) before styling it | XSS + layout-break from arbitrary scraped HTML | read/[id]/page.tsx `articleHtml` | M | eng

## Top 5 if you only do 5 things

1. Ship dark mode for the app (cheap given the token system, high perceived quality).
2. Fix the mobile web experience before any mobile-heavy launch traffic.
3. Do a basic a11y + reduced-motion pass.
4. Unify onboarding onto the design system (it's the first screen users see).
5. Make the landing hero degrade on touch/reduced-motion and self-host its images.

**Revisit trigger:** re-audit after dark mode + mobile pass, and before Product Hunt (design-sensitive audience).
