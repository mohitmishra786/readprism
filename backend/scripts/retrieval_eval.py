"""Print the fixture retrieval comparison. Does not download Nomic."""

from __future__ import annotations

from app.services.embeddings.retrieval import compare


def main() -> None:
    report = compare()
    print(
        "pairs={pairs} full_mrr={full_mrr:.4f} truncated_mrr={truncated_mrr:.4f} full_wins={full_wins}".format(
            **report
        )
    )
    if not report["full_wins"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
