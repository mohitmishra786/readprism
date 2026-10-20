import type { Metadata } from "next";
import { ComparisonPage, WEIRLING_PRICING } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "Weirling vs Readless: ranked digest vs AI newsletter summaries",
  description:
    "How Weirling compares to Readless: both send a daily digest. Readless summarizes your newsletters with AI; Weirling ranks feeds, newsletters and creators by how you actually read, and explains why.",
  alternates: { canonical: "/vs/readless" },
};

export default function VsReadless() {
  return (
    <ComparisonPage
      data={{
        competitor: "Readless",
        intro:
          "Readless turns your newsletters (and RSS feeds) into an AI-written daily email digest, highlighting topics covered by several senders. Weirling also sends a daily digest, but ranks it by what you actually read.",
        rows: [
          { dimension: "Sources", competitor: "Newsletters (own address), Substack, RSS", weirling: "RSS, newsletters (own address), creators across Substack, YouTube, Medium, Bluesky, Mastodon, GitHub" },
          { dimension: "Ranking basis", competitor: "AI summaries grouped by topic; no ranking by reading behavior", weirling: "8 reading signals with weights learned per reader" },
          { dimension: "Explainability", competitor: "Source references in Max briefings", weirling: "Per item: why it ranked where it did" },
          { dimension: "Pricing", competitor: "Pro $4.90/mo; Max $9/mo; 7-day trial with card; no free or annual plan", weirling: WEIRLING_PRICING },
          { dimension: "Self-hosting", competitor: "No", weirling: "Yes (Docker Compose, MIT)" },
        ],
        differsBecause: [
          "Readless summarizes everything you get; Weirling chooses what to show first, based on what you finish.",
          "Weirling explains each pick and lets you correct it.",
          "Weirling is open source; you can run it yourself for free.",
        ],
        fairnote:
          "Readless is focused and inexpensive for newsletter readers; Weirling is broader and built around personal ranking.",
        checked: "October 21, 2026",
        sources: [
          { label: "Readless pricing", url: "https://www.readless.app/pricing" },
        ],
      }}
    />
  );
}
