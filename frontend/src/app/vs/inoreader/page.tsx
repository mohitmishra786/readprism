import type { Metadata } from "next";
import { ComparisonPage } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "ReadPrism vs Inoreader — behavioral ranking vs AI summaries",
  description:
    "How ReadPrism compares to Inoreader: Inoreader added an AI layer (Intelligence + bring-your-own-AI in 2026) but still no behavioral ranking. ReadPrism ranks by how you actually read.",
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
          { dimension: "AI features", competitor: "Intelligence: summaries, smart tags, BYO OpenAI/Anthropic/Mistral key", readprism: "Summaries + a behavioral ranking engine" },
          { dimension: "Ranking basis", competitor: "Filtering/rules; no behavioral ranking", readprism: "8 behavioral signals + per-user learned weights" },
          { dimension: "Pricing", competitor: "Free (150 feeds, ads) / Pro ~$7.50/mo annual", readprism: "Full engine free; $4.99/mo Pro (planned)" },
          { dimension: "Self-hosting", competitor: "No", readprism: "Yes — Docker Compose, MIT-licensed" },
        ],
        differsBecause: [
          "Inoreader's AI summarizes and tags; ReadPrism additionally re-orders your digest by learned personal relevance.",
          "ReadPrism's ranking is explainable per item, down to the interest-graph connection.",
          "ReadPrism is open source and self-hostable; Inoreader is a hosted SaaS.",
        ],
        fairnote:
          "Inoreader is feature-rich with excellent filtering, monitoring, and a mature app; ReadPrism is focused specifically on behavioral, explainable ranking.",
      }}
    />
  );
}
