import type { Metadata } from "next";
import { ComparisonPage, WEIRLING_PRICING } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "Weirling vs Inoreader: behavioral ranking vs AI summaries",
  description:
    "How Weirling compares to Inoreader: Inoreader adds AI summaries and bring-your-own-key Intelligence, but not ranking by reading behavior. Weirling ranks by how you actually read.",
  alternates: { canonical: "/vs/inoreader" },
};

export default function VsInoreader() {
  return (
    <ComparisonPage
      data={{
        competitor: "Inoreader",
        intro:
          "Inoreader is a powerful RSS reader with an AI layer (Intelligence summaries, tags and reports, with your own OpenAI, Anthropic or Mistral key). What it doesn't have is ranking that learns from how you read.",
        rows: [
          { dimension: "AI features", competitor: "Intelligence: summaries, mentions, suggested tags, reports; bring your own API key", weirling: "Summaries plus a ranking engine that learns from your reading" },
          { dimension: "Ranking basis", competitor: "Rules, filters and monitoring; no ranking by reading behavior", weirling: "8 reading signals with weights learned per reader" },
          { dimension: "Pricing", competitor: "Free (150 feeds); Pro $7.50/mo billed yearly ($90) or $9.99 monthly, 2,500 feeds", weirling: WEIRLING_PRICING },
          { dimension: "Self-hosting", competitor: "No", weirling: "Yes (Docker Compose, MIT)" },
        ],
        differsBecause: [
          "Inoreader's AI summarizes and tags; Weirling also reorders your digest by learned personal relevance.",
          "Weirling's ranking is explainable per item, down to the interest-graph connection.",
          "Weirling is open source and self-hostable; Inoreader is a hosted service.",
        ],
        fairnote:
          "Inoreader is feature-rich, with excellent filtering, monitoring and mature apps; Weirling is focused on behavioral, explainable ranking.",
        checked: "October 21, 2026",
        sources: [
          { label: "Inoreader pricing", url: "https://www.inoreader.com/pricing" },
        ],
      }}
    />
  );
}
