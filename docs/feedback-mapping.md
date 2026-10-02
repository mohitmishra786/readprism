# Feedback → signal mapping (UX-06)

Every feedback control maps to documented learning effects. The code source
of truth is `backend/app/services/ranking/feedback_map.py`
(`REASON_EFFECTS`); this page is the human-readable table. Tests:
`backend/tests/test_api/test_feedback_reasons.py`.

## Reason tags (thumbs-down → "Why?")

| Tag | Label y | Confidence | Cluster weight | Source trust | Notes |
|---|---|---|---|---|---|
| `too_basic` | 0.35 | 0.8 | −0.10 | — | Also raises the depth expectation for the cluster (carried by the label; A4) |
| `already_knew` | 0.35 | 0.8 | −0.10 | — | Same behavior as `too_basic` |
| `off_topic` | 0.0 | 1.0 | −0.20 | — | Strongest cluster weakening (A4: "weaken that cluster link") |
| `too_tangential` | 0.0 | 1.0 | −0.20 | — | Legacy spelling of `off_topic`; same effect |
| `wrong_depth` | 0.45 | 0.6 | — | — | Calibration only: depth preference, not interest |
| `clickbait` | 0.20 | 0.8 | — | −0.10 | Source-quality failure, not an interest miss |

Behavior labels feed pairwise weight learning (A5); the cluster/source
effects are applied immediately when the tag is recorded
(`POST /api/v1/feedback/interaction`).

## Direct controls

| Control | Where | Mechanism |
|---|---|---|
| 👍 / 👎 | Digest cards, reader, email one-click | `explicit_rating` ±1 → label (1.0 / 0.0, c 1.0) |
| Save | Cards, reader, email one-click | `saved=true` → strong positive once read (UX-12 semantics) |
| Snooze topic | Preferences → interest graph (suppress, 30 d) | `POST /feedback/adjust-interests {action: suppress, duration_days}` |
| Mute source | Sources page | `PATCH /sources/{id} {is_active: false}` |
| Boost / suppress cluster | Preferences → interest graph | `POST /feedback/adjust-interests {action: boost \| suppress}` |

**Known gap (tracked in PROGRESS):** card-level "More like this / Less like
this" quick actions are not yet in the card UI; the mechanism
(`adjust-interests`) exists and is used by the interest-graph page.

## What each signal sees

- `explicit_feedback` (signal 4) — similarity-weighted mean of previously
  rated items, plus the depth/tangency adjustments.
- Interest-graph node weights — changed by the cluster deltas above and by
  direct controls; the graph drives the semantic signal's medoid weighting.
- `source_trust` (signal 5) — Beta posterior over per-source behavior; the
  clickbait delta nudges its prior (`sources.trust_weight`).
