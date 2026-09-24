"""Print the offline extraction report. Pages are generated, not downloaded."""

from __future__ import annotations

from app.services.ingestion.golden import evaluate


def main() -> None:
    report = evaluate()
    print(
        "articles={articles} word_f1={word_f1:.3f} snippet_recall={snippet_recall:.3f} "
        "listings_unrankable={listings_unrankable}/{listings} methods={methods}".format(**report)
    )
    if report["word_f1"] < 0.90 or report["snippet_recall"] < 0.90:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
