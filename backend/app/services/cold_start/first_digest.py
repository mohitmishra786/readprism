"""First-digest quality gate (CS-05).

A new user's first digest must prove itself: enough items, enough topic
spread, at least one discovery item, no duplicates, and mostly readable
summaries. Pure check; the CI test seeds a realistic fresh instance and
runs the real digest builder through it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MIN_ITEMS = 5
MIN_CLUSTERS = 3
MIN_DISCOVERY = 1
MIN_SUMMARY_RATIO = 0.80


@dataclass
class FirstDigestReport:
    item_count: int = 0
    cluster_count: int = 0
    discovery_count: int = 0
    duplicate_urls: list[str] = field(default_factory=list)
    items_with_summary: int = 0
    passed: bool = False

    def reasons(self) -> list[str]:
        why = []
        if self.item_count < MIN_ITEMS:
            why.append(f"items {self.item_count} < {MIN_ITEMS}")
        if self.cluster_count < MIN_CLUSTERS:
            why.append(f"clusters {self.cluster_count} < {MIN_CLUSTERS}")
        if self.discovery_count < MIN_DISCOVERY:
            why.append(f"discovery {self.discovery_count} < {MIN_DISCOVERY}")
        if self.duplicate_urls:
            why.append(f"duplicates: {self.duplicate_urls}")
        if self.items_with_summary < round(MIN_SUMMARY_RATIO * self.item_count):
            why.append(
                f"summaries {self.items_with_summary}/{self.item_count} < {MIN_SUMMARY_RATIO:.0%}"
            )
        return why


def first_digest_quality(items: list[dict]) -> FirstDigestReport:
    """items: [{url, topic_clusters, origin, summary}] — one per digest entry."""
    report = FirstDigestReport()
    report.item_count = len(items)
    seen_urls: set[str] = set()
    clusters: set[str] = set()
    for item in items:
        url = item.get("url", "")
        if url in seen_urls:
            report.duplicate_urls.append(url)
        seen_urls.add(url)
        clusters.update(item.get("topic_clusters") or [])
        if item.get("origin") == "discovery":
            report.discovery_count += 1
        if (item.get("summary") or "").strip():
            report.items_with_summary += 1
    report.cluster_count = len(clusters)
    report.passed = not report.reasons()
    return report
