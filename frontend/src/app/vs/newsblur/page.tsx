import type { Metadata } from "next";
import { ComparisonPage } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "Weirling vs NewsBlur: semantic + telemetry vs keyword training",
  description:
    "How Weirling compares to NewsBlur, the closest analog: NewsBlur's Intelligence trains on keyword/author/tag like-dislike; Weirling uses semantic embeddings + real reading telemetry and an interest graph.",
  alternates: { canonical: "/vs/newsblur" },
};

export default function VsNewsBlur() {
  return (
    <ComparisonPage
      data={{
        competitor: "NewsBlur",
        intro:
          "NewsBlur is the closest analog to Weirling: it has a genuinely trainable per-user ranking (its Intelligence Trainer) and is open source. The difference is what the training is based on.",
        rows: [
          { dimension: "Ranking basis", competitor: "Train on like/dislike of keywords, authors, tags (transparent, Bayes-style)", weirling: "Semantic embeddings + real reading telemetry (scroll depth, active time) + interest graph" },
          { dimension: "Interest model", competitor: "Flat per-feed classifiers", weirling: "Decaying interest graph with transitive (2-hop) relevance" },
          { dimension: "Signal source", competitor: "Explicit like/dislike training", weirling: "Behavioral telemetry + explicit feedback + suggestion reads" },
          { dimension: "Pricing", competitor: "$36/yr Premium", weirling: "Full engine free; $4.99/mo Pro (planned)" },
          { dimension: "Self-hosting", competitor: "Yes (open source)", weirling: "Yes (Docker Compose, MIT)" },
        ],
        differsBecause: [
          "NewsBlur trains on keyword/author/tag likes you set; Weirling learns from how you actually read (semantic + behavioral), so it needs less manual training but more reading history.",
          "Weirling models interests as a graph with transitive relevance, not flat per-feed classifiers.",
          "Both are open source and self-hostable. This is the friendliest comparison: NewsBlur is more mature, Weirling's wedge is telemetry-driven semantic ranking.",
        ],
        fairnote:
          "NewsBlur is a mature, well-loved product with years of refinement and a sustainable indie business. Weirling is earlier; the honest pitch is a different ranking mechanism, not a strictly better product.",
      }}
    />
  );
}
