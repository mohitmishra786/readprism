import type { Metadata } from "next";
import { ComparisonPage, WEIRLING_PRICING } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "Weirling vs NewsBlur: reading signals vs a trainable classifier",
  description:
    "How Weirling compares to NewsBlur: both are open source and self-hostable with personal ranking. NewsBlur trains on your likes and dislikes; Weirling learns from how you actually read.",
  alternates: { canonical: "/vs/newsblur" },
};

export default function VsNewsBlur() {
  return (
    <ComparisonPage
      data={{
        competitor: "NewsBlur",
        intro:
          "NewsBlur is the closest analog to Weirling: it has a genuinely trainable per-user ranking (the Intelligence Trainer) and is open source. The difference is what the training is based on.",
        rows: [
          { dimension: "Ranking basis", competitor: "Train on likes and dislikes of keywords, authors, tags (transparent, Bayes style)", weirling: "Semantic embeddings plus real reading telemetry (scroll depth, active time, completion)" },
          { dimension: "Interest model", competitor: "Per-feed classifiers", weirling: "Decaying interest graph with two-hop topic relevance" },
          { dimension: "Signal source", competitor: "Explicit like and dislike training", weirling: "Reading behavior, explicit feedback and what you open from suggestions" },
          { dimension: "Pricing", competitor: "Free (64 sites); Premium $36/yr (1,024 sites); Archive $99/yr (4,096); Pro $29/mo (10,000)", weirling: WEIRLING_PRICING },
          { dimension: "Self-hosting", competitor: "Yes (open source, Docker)", weirling: "Yes (Docker Compose, MIT)" },
        ],
        differsBecause: [
          "NewsBlur learns from what you mark; Weirling learns from what you actually read, without extra clicks.",
          "Weirling builds a topic graph across sources, so related articles rank even when they share no keywords.",
          "Every Weirling pick comes with the reason, in plain words.",
        ],
        fairnote:
          "Both are open source and self-hostable. NewsBlur is more mature; Weirling's difference is ranking by reading behavior and meaning.",
        checked: "October 21, 2026",
        sources: [
          { label: "NewsBlur pricing", url: "https://newsblur.com/pricing" },
        ],
      }}
    />
  );
}
