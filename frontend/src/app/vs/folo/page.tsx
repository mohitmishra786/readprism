import type { Metadata } from "next";
import { ComparisonPage, WEIRLING_PRICING } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "Weirling vs Folo: ranking by reading vs an AI timeline",
  description:
    "How Weirling compares to Folo, the open-source AI RSS reader: Folo adds AI summaries, translation and rule-based actions to a timeline; Weirling ranks a daily digest by how you actually read.",
  alternates: { canonical: "/vs/folo" },
};

export default function VsFolo() {
  return (
    <ComparisonPage
      data={{
        competitor: "Folo",
        intro:
          "Folo is a popular open-source RSS reader with AI summaries, translation and automation (actions), plus bring-your-own-key on its higher plans. Weirling is built around one daily digest ranked by your reading.",
        rows: [
          { dimension: "Core idea", competitor: "A fast timeline of everything you follow, with AI on top", weirling: "One short daily digest, ranked for you" },
          { dimension: "Ranking basis", competitor: "Timeline with rule-based actions; no ranking by reading behavior advertised", weirling: "8 reading signals with weights learned per reader" },
          { dimension: "AI", competitor: "Summaries (3/day free, 30/day Basic, unlimited Plus), translation, bring your own key on Plus and Pro", weirling: "Summaries, story synthesis, explanations; bring your own key" },
          { dimension: "Pricing", competitor: "Free (150 feeds); Basic $49.99/yr (1,000); Plus $99.99/yr (2,500); Pro $999.99/yr (25,000)", weirling: WEIRLING_PRICING },
          { dimension: "License", competitor: "Open source (AGPL-3.0)", weirling: "Open source (MIT), self-hostable with Docker Compose" },
        ],
        differsBecause: [
          "Folo shows you everything, faster; Weirling decides what is worth your time today and says why.",
          "Weirling learns from scroll depth, active reading time and what you finish, with no rules to write.",
          "Weirling's self-hosted edition has every feature, under the MIT license.",
        ],
        fairnote:
          "Folo is polished, fast and great for people who want to see every item. Weirling is for people who want fewer, better items.",
        checked: "October 21, 2026",
        sources: [
          { label: "Folo pricing", url: "https://folo.is/pricing" },
          { label: "Folo source code and license", url: "https://github.com/RSSNext/Folo" },
        ],
      }}
    />
  );
}
