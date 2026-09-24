# Ranking signals

Each value is in [0, 1] and is computed before the user sees the item.

| Signal | Meaning |
|---|---|
| semantic | Importance-weighted max cosine against the top interest medoids |
| reading_depth | Predicted completion from other items of the same source and length. The candidate's own interaction is excluded |
| suggestion | Higher when the item's origin is `discovery` |
| explicit_feedback | Thumbs, saves, and skips. A skip counts only if the digest was viewed |
| source_trust | Time-decayed Beta mean for the source. New sources start at the prior |
| content_quality | Length, links, citations, and code, shrunk toward the user's completion for that length |
| temporal_context | Long, medium, and short recency, with a saturation penalty for a repeated event |
| novelty | Distance from what the user already reads |

Contributions are the user's ranker weight times the signal. They sum to the linear score before that score is clamped to [0, 1]. The clamp can make the stored PRS differ from the sum.
