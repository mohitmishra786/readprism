import type { Metadata } from "next";
import { ComparisonPage } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "ReadPrism vs NewsBlur — semantic + telemetry vs keyword training",
  description:
    "How ReadPrism compares to NewsBlur, the closest analog: NewsBlur's Intelligence trains on keyword/author/tag like-dislike; ReadPrism uses semantic embeddings + real reading telemetry and an interest graph.",
  alternates: { canonical: "/vs/newsblur" },
};

export default function VsNewsBlur() {
  return (
    <ComparisonPage
      data={{
        competitor: "NewsBlur",
        intro:
          "NewsBlur is the closest analog to ReadPrism — it has a genuinely trainable per-user ranking (its Intelligence Trainer) and is open source. The difference is what the training is based on.",
        rows: [
          { dimension: "Ranking basis", competitor: "Train on like/dislike of keywords, authors, tags (transparent, Bayes-style)", readprism: "Semantic embeddings + real reading telemetry (scroll depth, active time) + interest graph" },
          { dimension: "Interest model", competitor: "Flat per-feed classifiers", readprism: "Decaying interest graph with transitive (2-hop) relevance" },
          { dimension: "Signal source", competitor: "Explicit like/dislike training", readprism: "Behavioral telemetry + explicit feedback + suggestion reads" },
          { dimension: "Pricing", competitor: "$36/yr Premium", readprism: "Full engine free; $4.99/mo Pro (planned)" },
          { dimension: "Self-hosting", competitor: "Yes (open source)", readprism: "Yes — Docker Compose, MIT-licensed" },
        ],
        differsBecause: [
          "NewsBlur trains on keyword/author/tag likes you set; ReadPrism learns from how you actually read (semantic + behavioral), so it needs less manual training but more reading history.",
          "ReadPrism models interests as a graph with transitive relevance, not flat per-feed classifiers.",
          "Both are open source and self-hostable — this is the friendliest comparison; NewsBlur is more mature, ReadPrism's wedge is telemetry-driven semantic ranking.",
        ],
        fairnote:
          "NewsBlur is a mature, well-loved product with years of refinement and a sustainable indie business. ReadPrism is earlier; the honest pitch is a different ranking mechanism, not a strictly better product.",
      }}
    />
  );
}
