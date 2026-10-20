import type { Metadata } from "next";
import { ComparisonPage } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "Weirling vs Inoreader: behavioral ranking vs AI summaries",
  description:
    "How Weirling compares to Inoreader: Inoreader added an AI layer (Intelligence + bring-your-own-AI in 2026) but still no behavioral ranking. Weirling ranks by how you actually read.",
  alternates: { canonical: "/vs/inoreader" },
};

export default function VsInoreader() {
  return (
    <ComparisonPage
      data={{
        competitor: "Inoreader",
        intro:
          "Inoreader is a powerful RSS reader that, as of 2026, has an AI layer (Intelligence summaries + bring-your-own-AI). What it still doesn't have is ranking that learns from your reading behavior.",
        rows: [
          { dimension: "AI features", competitor: "Intelligence: summaries, smart tags, BYO OpenAI/Anthropic/Mistral key", weirling: "Summaries + a behavioral ranking engine" },
          { dimension: "Ranking basis", competitor: "Filtering/rules; no behavioral ranking", weirling: "8 behavioral signals + per-user learned weights" },
          { dimension: "Pricing", competitor: "Free (150 feeds, ads) / Pro ~$7.50/mo annual", weirling: "Full engine free; $4.99/mo Pro (planned)" },
          { dimension: "Self-hosting", competitor: "No", weirling: "Yes (Docker Compose, MIT)" },
        ],
        differsBecause: [
          "Inoreader's AI summarizes and tags; Weirling additionally re-orders your digest by learned personal relevance.",
          "Weirling's ranking is explainable per item, down to the interest-graph connection.",
          "Weirling is open source and self-hostable; Inoreader is a hosted SaaS.",
        ],
        fairnote:
          "Inoreader is feature-rich with excellent filtering, monitoring, and a mature app; Weirling is focused specifically on behavioral, explainable ranking.",
      }}
    />
  );
}
