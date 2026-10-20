"""Offline replay of a reader's own logs (#200), on a synthetic export."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.services.embeddings.registry import hash_embed
from app.services.ranking.replay import evaluate, ndcg_at, recall_at, report_markdown, split

NOW = datetime(2026, 10, 20, 7, tzinfo=UTC)


def _encode(texts):
    return np.array([hash_embed(t, 384) for t in texts], dtype=np.float32)


def _export(days: int = 21) -> dict:
    """A reader who finishes database posts and skips gardening posts."""
    db_src, garden_src = str(uuid.uuid4()), str(uuid.uuid4())
    content, interactions, digests, digest_items = [], [], [], []
    db_words = "postgres vacuum index planner btree wal replication query".split()
    garden_words = "tomato compost seedling soil mulch harvest beans pruning".split()
    for day in range(days, 0, -1):
        when = NOW - timedelta(days=day)
        digest_id = str(uuid.uuid4())
        digests.append({"id": digest_id, "generated_at": when.isoformat()})
        for pos in range(6):
            topic = "db" if pos % 2 == 0 else "garden"
            words = db_words if topic == "db" else garden_words
            cid = str(uuid.uuid4())
            # Gardening items are always newer, so newest-first prefers them.
            fetched = when - timedelta(hours=(10 - pos) if topic == "db" else 1 + pos * 0.1)
            content.append(
                {
                    "id": cid,
                    "url": f"https://x.example/{cid}",
                    "title": " ".join(words[(day + pos) % 4 : (day + pos) % 4 + 4]),
                    "summary_brief": " ".join(words),
                    "topic_clusters": [topic],
                    "source_id": db_src if topic == "db" else garden_src,
                    "fetched_at": fetched.isoformat(),
                    "published_at": fetched.isoformat(),
                    "word_count": 900,
                }
            )
            digest_items.append({"digest_id": digest_id, "content_item_id": cid, "position": pos})
            finished = topic == "db"
            interactions.append(
                {
                    "content_item_id": cid,
                    "created_at": (when + timedelta(hours=2)).isoformat(),
                    "opened_at": (when + timedelta(hours=2)).isoformat(),
                    "read_completion_pct": 0.95 if finished else 0.05,
                    "reached_end": finished,
                    "skipped": not finished,
                    "saved": False,
                    "explicit_rating": None,
                }
            )
    return {
        "export_metadata": {"format_version": 2},
        "sources": [
            {
                "id": db_src,
                "url": "https://db.example/",
                "feed_url": "https://db.example/f",
                "name": "DB",
            },
            {
                "id": garden_src,
                "url": "https://g.example/",
                "feed_url": "https://g.example/f",
                "name": "Garden",
            },
        ],
        "interest_nodes": [{"topic_label": "postgres internals", "weight": 0.8}],
        "content": content,
        "interactions": interactions,
        "digests": digests,
        "digest_items": digest_items,
    }


def test_metrics():
    assert ndcg_at(["a", "b", "c"], {"a"}) == pytest.approx(1.0)
    assert ndcg_at(["b", "a"], {"a"}) == pytest.approx(1 / np.log2(3))
    assert recall_at(["a", "b", "c", "d", "e", "f"], {"a", "f"}) == 0.5


def test_split_never_trains_on_the_test_week():
    sp = split(_export(), test_days=7)
    assert len(sp.test_digests) == 7
    assert all(datetime.fromisoformat(ix["created_at"]) < sp.cutoff for ix in sp.train)
    assert all(relevant for _, _, relevant in sp.test_digests)


def test_prs_beats_newest_first_on_a_reader_with_clear_tastes():
    result = evaluate(_export(), _encode, test_days=7)
    prs, newest = result["rankers"]["prs"], result["rankers"]["newest_first"]
    assert result["test_digests_used"] == 7
    assert prs["ndcg@10"] > newest["ndcg@10"]
    assert prs["recall@5"] >= newest["recall@5"]
    report = report_markdown(result, label="synthetic")
    assert "| PRS (ReadPrism) |" in report and "x.example" not in report  # aggregate only


def test_old_exports_are_rejected_with_a_clear_message(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    old = tmp_path / "old.json"
    old.write_text(json.dumps({"export_metadata": {"format_version": 1}}))
    script = Path(__file__).resolve().parents[2] / "scripts" / "replay_eval.py"
    proc = subprocess.run([sys.executable, str(script), str(old)], capture_output=True, text=True)
    assert proc.returncode != 0 and "format 2" in proc.stderr
