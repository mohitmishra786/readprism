"""Write docs/eval/ranking.md from the synthetic harness."""

from __future__ import annotations

from pathlib import Path

from app.services.ranking.phase2.learning import synthetic_eval


def main() -> None:
    report = synthetic_eval()
    backend = Path(__file__).resolve().parents[1]
    root = backend.parent if (backend.parent / "docs").is_dir() else backend
    target = root / "docs" / "eval" / "ranking.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "# Ranking eval",
                "",
                "Synthetic users, one dominant signal each. PRS ranks by that signal.",
                "Chronological keeps ingest order. Semantic-only uses the first feature.",
                "Random is a permutation. NDCG@10 is the mean across users.",
                "",
                f"- PRS NDCG@10: {report.prs_ndcg:.4f}",
                f"- Chronological NDCG@10: {report.chronological_ndcg:.4f}",
                f"- Semantic-only NDCG@10: {report.semantic_ndcg:.4f}",
                f"- Random NDCG@10: {report.random_ndcg:.4f}",
                f"- Margin over chronological: {report.margin:.4f}",
                "",
                "Gate: PRS beats each baseline by at least 0.05.",
                f"Passed: {report.beats_baselines()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(target)
    if not report.beats_baselines():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
