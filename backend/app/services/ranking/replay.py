"""Offline replay of a reader's own logs (#200).

Input is the account export (format 2: interactions, digests, digest_items,
content). Nothing touches a database or the network, so the owner can run it
on their own export and only the aggregate report leaves their machine.

Protocol (pre-registered in docs/eval/replay-protocol.md):
- split: digests from the last TEST_DAYS days are the test set; everything
  the ranker learns from is restricted to interactions created before the
  first test digest (leave-last-week-out);
- candidates: the items each test digest actually showed;
- relevant: an item the reader fully read (completion >= 0.85 or reached
  the end), saved, or rated up;
- rankers: PRS (score_candidates on a state rebuilt from training data only,
  default contract weights), newest-first, and trust-only (per-feed finish
  rate in the training data);
- metrics: NDCG@10 and recall@5 per digest, averaged over test digests with
  at least one relevant item.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

TEST_DAYS = 7
FINISHED = 0.85


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def is_relevant(ix: dict) -> bool:
    completion = ix.get("read_completion_pct") or 0.0
    return bool(
        completion >= FINISHED
        or ix.get("reached_end")
        or ix.get("saved")
        or (ix.get("explicit_rating") or 0) > 0
    )


def ndcg_at(ranked: Sequence[str], relevant: set[str], k: int = 10) -> float:
    dcg = sum(1 / math.log2(i + 2) for i, cid in enumerate(ranked[:k]) if cid in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def recall_at(ranked: Sequence[str], relevant: set[str], k: int = 5) -> float:
    return len(set(ranked[:k]) & relevant) / len(relevant) if relevant else 0.0


@dataclass
class ReplaySplit:
    cutoff: datetime
    train: list[dict]
    test_digests: list[tuple[dict, list[str], set[str]]]  # digest, shown ids, relevant ids


def split(export: dict, test_days: int = TEST_DAYS) -> ReplaySplit:
    dated = sorted(
        (
            (moment, d)
            for d in export.get("digests", [])
            if (moment := _ts(d.get("generated_at"))) is not None
        ),
        key=lambda pair: pair[0],
    )
    if not dated:
        raise ValueError("the export has no digests to replay")
    window_start = dated[-1][0] - timedelta(days=test_days)
    test_pairs = [(moment, d) for moment, d in dated if moment > window_start]
    test = [d for _, d in test_pairs]
    cutoff = test_pairs[0][0]

    def created(ix: dict) -> datetime:
        return _ts(ix.get("created_at")) or cutoff

    train = [ix for ix in export.get("interactions", []) if created(ix) < cutoff]
    by_digest: dict[str, list[dict]] = {}
    for row in export.get("digest_items", []):
        by_digest.setdefault(row["digest_id"], []).append(row)
    interactions = {ix["content_item_id"]: ix for ix in export.get("interactions", [])}
    cases = []
    for digest in test:
        rows = sorted(by_digest.get(digest["id"], []), key=lambda r: r["position"])
        shown = [r["content_item_id"] for r in rows]
        relevant = {cid for cid in shown if cid in interactions and is_relevant(interactions[cid])}
        cases.append((digest, shown, relevant))
    return ReplaySplit(cutoff=cutoff, train=train, test_digests=cases)


def _content_item(row: dict, vector: np.ndarray | None):
    from app.models.content import ContentItem

    item = ContentItem(
        id=uuid.UUID(row["id"]),
        url=row.get("url") or "",
        title=row.get("title") or "",
        author=row.get("author"),
        summary_brief=row.get("summary_brief"),
        topic_clusters=row.get("topic_clusters") or [],
        source_id=uuid.UUID(row["source_id"]) if row.get("source_id") else None,
        feed_id=uuid.UUID(row["feed_id"]) if row.get("feed_id") else None,
        origin=row.get("origin") or "followed",
        published_at=_ts(row.get("published_at")),
        fetched_at=_ts(row.get("fetched_at")),
        word_count=row.get("word_count") or 0,
        reading_time_minutes=row.get("reading_time_minutes"),
        has_citations=bool(row.get("has_citations")),
        content_depth_score=row.get("content_depth_score"),
        is_original_reporting=row.get("is_original_reporting"),
    )
    item.embedding = None if vector is None else vector.tolist()
    return item


def _feed_key(source: dict) -> str:
    return source.get("feed_url") or source.get("url") or str(source.get("id"))


def build_state(export: dict, sp: ReplaySplit, vectors: dict[str, np.ndarray], now: datetime):
    """A ranker state from training data only (no leakage from the test week)."""
    from app.services.ranking.contract import SIGNALS
    from app.services.ranking.ranker import FeedState, HistoryRow, Interest, UserRankingState

    content = {row["id"]: row for row in export.get("content", [])}
    sources = {s["id"]: s for s in export.get("sources", [])}
    source_key = {uuid.UUID(sid): _feed_key(s) for sid, s in sources.items()}

    history = []
    feeds: dict[str, FeedState] = {
        _feed_key(s): FeedState(name=s.get("name") or _feed_key(s), trust_weight=0.5)
        for s in sources.values()
    }
    for ix in sp.train:
        row = content.get(ix["content_item_id"], {})
        sid = row.get("source_id")
        key = source_key.get(uuid.UUID(sid)) if sid else None
        history.append(
            HistoryRow(
                content_id=uuid.UUID(ix["content_item_id"]),
                vector=vectors.get(ix["content_item_id"]),
                feed_key=key,
                words=int(row.get("word_count") or 0),
                completion=ix.get("read_completion_pct"),
                rating=ix.get("explicit_rating"),
                reason=ix.get("explicit_rating_reason"),
                saved=bool(ix.get("saved")),
                skipped=bool(ix.get("skipped")),
                was_suggested=bool(ix.get("was_suggested")),
                opened_at=_ts(ix.get("opened_at")),
                created_at=_ts(ix.get("created_at")) or now,
                published_at=_ts(row.get("published_at")),
                title=row.get("title") or "",
            )
        )
        if key in feeds:
            if is_relevant(ix):
                feeds[key].successes += 1
            elif ix.get("skipped") or (ix.get("read_completion_pct") or 0) < 0.2:
                feeds[key].failures += 1

    # Interests: the reader's own topic labels, re-embedded (vectors are not
    # exported). Importance from the exported weights.
    interests = [
        Interest(
            vector=vectors[f"interest:{node['topic_label']}"],
            importance=float(node.get("weight") or 0.5),
            label=node["topic_label"],
        )
        for node in export.get("interest_nodes", [])
        if f"interest:{node['topic_label']}" in vectors
    ]
    weights = {name: 1 / len(SIGNALS) for name in SIGNALS}
    return UserRankingState(
        user_id=uuid.uuid4(),
        weights=weights,
        history=history,
        interests=interests,
        bridges=[],
        feeds=feeds,
        source_feed_key=source_key,
        prefers_fresh=True,
        novelty_target=0.35,
        now=now,
    )


def embed_all(export: dict, encode: Callable[[list[str]], np.ndarray]) -> dict[str, np.ndarray]:
    """Vectors for every exported article and interest label, with the local model."""
    keys, texts = [], []
    for row in export.get("content", []):
        keys.append(row["id"])
        texts.append(f"{row.get('title') or ''}. {row.get('summary_brief') or ''}")
    for node in export.get("interest_nodes", []):
        keys.append(f"interest:{node['topic_label']}")
        texts.append(node["topic_label"])
    if not texts:
        return {}
    matrix = np.asarray(encode(texts), dtype=np.float32)
    return dict(zip(keys, matrix, strict=True))


def evaluate(
    export: dict, encode: Callable[[list[str]], np.ndarray], test_days: int = TEST_DAYS
) -> dict:
    from app.services.ranking.ranker import score_candidates

    sp = split(export, test_days)
    vectors = embed_all(export, encode)
    content = {row["id"]: row for row in export.get("content", [])}
    sources = {s["id"]: s for s in export.get("sources", [])}

    results: dict[str, dict[str, list[float]]] = {
        name: {"ndcg@10": [], "recall@5": []} for name in ("prs", "newest_first", "trust_only")
    }
    used = 0
    for digest, shown, relevant in sp.test_digests:
        rows = [content[cid] for cid in shown if cid in content]
        if not relevant or len(rows) < 2:
            continue
        used += 1
        now = _ts(digest["generated_at"]) or datetime.now(UTC)
        state = build_state(export, sp, vectors, now)
        items = [_content_item(r, vectors.get(r["id"])) for r in rows]

        prs = [
            str(s.item.id)
            for s in sorted(score_candidates(state, items), key=lambda s: s.prs, reverse=True)
        ]
        newest = [
            r["id"] for r in sorted(rows, key=lambda r: r.get("fetched_at") or "", reverse=True)
        ]

        def trust(row: dict, feeds: dict = state.feeds) -> float:
            source = sources.get(row.get("source_id") or "")
            feed = feeds.get(_feed_key(source)) if source else None
            if feed is None:
                return 0.5
            return (feed.successes + 1) / (feed.successes + feed.failures + 2)

        trust_only = [
            r["id"]
            for r in sorted(rows, key=lambda r: (trust(r), r.get("fetched_at") or ""), reverse=True)
        ]

        for name, ranked in (("prs", prs), ("newest_first", newest), ("trust_only", trust_only)):
            results[name]["ndcg@10"].append(ndcg_at(ranked, relevant))
            results[name]["recall@5"].append(recall_at(ranked, relevant))

    summary = {
        name: {
            metric: (sum(vals) / len(vals) if vals else None) for metric, vals in metrics.items()
        }
        for name, metrics in results.items()
    }
    return {
        "test_days": test_days,
        "cutoff": sp.cutoff.isoformat(),
        "train_interactions": len(sp.train),
        "test_digests": len(sp.test_digests),
        "test_digests_used": used,
        "relevant_items": sum(len(r) for _, _, r in sp.test_digests),
        "rankers": summary,
    }


def report_markdown(result: dict, *, label: str) -> str:
    lines = [
        f"# Offline replay: {label}",
        "",
        "Protocol: [replay-protocol.md](replay-protocol.md) (pre-registered).",
        "",
        f"- Training: {result['train_interactions']} interactions before {result['cutoff'][:10]}",
        f"- Test: {result['test_digests_used']} of {result['test_digests']} digests from the last "
        f"{result['test_days']} days had at least one relevant item "
        f"({result['relevant_items']} relevant items in total)",
        "",
        "| Ranker | NDCG@10 | Recall@5 |",
        "|---|---|---|",
    ]
    names = {"prs": "PRS (ReadPrism)", "newest_first": "Newest first", "trust_only": "Trust only"}
    for key, name in names.items():
        row = result["rankers"][key]
        fmt = lambda v: "n/a" if v is None else f"{v:.3f}"  # noqa: E731
        lines.append(f"| {name} | {fmt(row['ndcg@10'])} | {fmt(row['recall@5'])} |")
    return "\n".join(lines) + "\n"
