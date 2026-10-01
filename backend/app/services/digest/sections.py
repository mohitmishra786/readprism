from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.models.content import ContentItem


@dataclass
class DigestSection:
    name: str
    items: list[tuple[ContentItem, float, dict]] = field(default_factory=list)
    max_items: int = 5

    def add(self, item: ContentItem, prs: float, breakdown: dict) -> bool:
        if len(self.items) >= self.max_items:
            return False
        self.items.append((item, prs, breakdown))
        return True

    def is_full(self) -> bool:
        return len(self.items) >= self.max_items


class SectionBuilder:
    def __init__(
        self,
        total_items: int,
        serendipity_pct: int = 15,
        max_topic_pct: float = 0.30,
    ) -> None:
        self.total_items = total_items
        self.serendipity_pct = serendipity_pct
        self.max_topic_pct = max_topic_pct
        self.discovery_count = max(1, math.ceil(total_items * serendipity_pct / 100))
        # Spec (A6): Lead = top 3–5 items. Scale with digest size, clamp to 3–5
        # (and to the digest size itself for very small digests).
        self.lead_count = max(1, min(5, total_items, max(3, round(total_items * 0.35))))

    def is_lead_eligible(
        self, content: ContentItem, prs: float, breakdown: dict | None = None
    ) -> bool:
        # Exploration slots never lead (A6: "top 3–5 (non-exploration)").
        return not (breakdown or {}).get("exploration", False)

    def is_deep_read_eligible(self, content: ContentItem) -> bool:
        return (content.reading_time_minutes or 0) >= 8

    def is_discovery_eligible(self, content: ContentItem, breakdown: dict) -> bool:
        # Discovery = items from the discovery pool (origin=discovery) plus the
        # serendipity picks flagged by the digest builder. It is NOT "whatever
        # followed item scored lowest".
        return content is not None and (
            getattr(content, "origin", None) == "discovery"
            or breakdown.get("_serendipity_candidate", False)
        )

    def build(
        self,
        ranked_items: list[tuple[ContentItem, float, dict]],
    ) -> dict[str, DigestSection]:
        sections: dict[str, DigestSection] = {
            "lead": DigestSection("lead", max_items=self.lead_count),
            "creator": DigestSection("creator", max_items=max(1, self.total_items // 4)),
            "deep_reads": DigestSection("deep_reads", max_items=max(1, self.total_items // 5)),
            "discovery": DigestSection("discovery", max_items=self.discovery_count),
        }

        used_ids: set = set()
        topic_counts: dict[str, int] = {}
        max_per_topic = max(1, math.floor(self.total_items * self.max_topic_pct))

        def _check_saturation(content: ContentItem) -> bool:
            for topic in content.topic_clusters or []:
                if topic_counts.get(topic, 0) >= max_per_topic:
                    return False
            return True

        def _update_topics(content: ContentItem) -> None:
            for topic in content.topic_clusters or []:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

        # Discovery section first (serendipity candidates)
        for item, prs, breakdown in ranked_items:
            if self.is_discovery_eligible(item, breakdown) and item.id not in used_ids:
                if sections["discovery"].add(item, prs, breakdown):
                    used_ids.add(item.id)
                    _update_topics(item)
            if sections["discovery"].is_full():
                break

        # Lead section (top non-exploration items)
        for item, prs, breakdown in ranked_items:
            if item.id in used_ids:
                continue
            if not self.is_lead_eligible(item, prs, breakdown):
                continue
            if not _check_saturation(item):
                continue
            if sections["lead"].add(item, prs, breakdown):
                used_ids.add(item.id)
                _update_topics(item)
            if sections["lead"].is_full():
                break

        # Creator section - group by creator, take top 1-2 per creator,
        # keep each creator's items contiguous (spec: "grouped by person").
        # Creators are ordered by their best PRS.
        creator_rows: dict[str, list[tuple[ContentItem, float, dict]]] = {}
        creator_best: dict[str, float] = {}
        for item, prs, breakdown in ranked_items:
            if item.id in used_ids or item.creator_platform_id is None:
                continue
            if not _check_saturation(item):
                continue
            cid = str(item.creator_platform_id)
            if len(creator_rows.get(cid, [])) >= 2:
                continue
            creator_rows.setdefault(cid, []).append((item, prs, breakdown))
            creator_best[cid] = max(creator_best.get(cid, 0.0), prs)

        for cid in sorted(creator_rows, key=lambda c: creator_best[c], reverse=True):
            for row in creator_rows[cid]:
                # Recheck saturation at emit time: the preselection pass ran
                # before any creator row was counted, so same-topic rows can
                # each have passed individually and then overflow the cap.
                if not _check_saturation(row[0]):
                    continue
                if sections["creator"].add(*row):
                    used_ids.add(row[0].id)
                    _update_topics(row[0])

        # Deep reads section
        for item, prs, breakdown in ranked_items:
            if item.id in used_ids:
                continue
            if not self.is_deep_read_eligible(item):
                continue
            if not _check_saturation(item):
                continue
            if sections["deep_reads"].add(item, prs, breakdown):
                used_ids.add(item.id)
                _update_topics(item)
            if sections["deep_reads"].is_full():
                break

        return sections
