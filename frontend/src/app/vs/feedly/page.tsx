import type { Metadata } from "next";
import { ComparisonPage, WEIRLING_PRICING } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "Weirling vs Feedly: behavioral ranking vs keyword rules",
  description:
    "How Weirling compares to Feedly: ranking that learns from how you actually read, explained per item, versus Feedly AI's topic and keyword rules. Open source and self-hostable.",
  alternates: { canonical: "/vs/feedly" },
};

export default function VsFeedly() {
  return (
    <ComparisonPage
      data={{
        competitor: "Feedly",
        intro:
          "Feedly is the incumbent RSS reader. Its AI (Leo) prioritizes by topics, keywords and examples you train it on. Weirling ranks by how you actually read and explains every pick.",
        rows: [
          { dimension: "Ranking basis", competitor: "AI feeds and priorities trained on topics, keywords and examples (Pro+)", weirling: "8 reading signals with weights learned per reader" },
          { dimension: "Explainability", competitor: "Shows which priority matched", weirling: "Per item: the signals behind its rank and the topic connection" },
          { dimension: "Pricing", competitor: "Free (100 sources); Pro about $6 to $7/mo billed yearly; Pro+ about $12/mo billed yearly, with a first-year offer of $99", weirling: WEIRLING_PRICING },
          { dimension: "Self-hosting", competitor: "No", weirling: "Yes (Docker Compose, MIT)" },
        ],
        differsBecause: [
          "Behavioral, not keyword: Weirling learns from scroll depth, active reading time and what you finish, not rules you maintain by hand.",
          "Explainable: every item shows the signals that drove it and, when relevant, the topic connection.",
          "Open and self-hostable: the full ranking engine is free and the code is yours to run.",
        ],
        fairnote:
          "Feedly is a mature product with broad integrations and a large free tier; Weirling is earlier and narrower, focused on behavioral ranking.",
        checked: "October 21, 2026",
        sources: [
          { label: "Feedly pricing (Pro and Pro+, first-year offer), checked Oct 16, 2026 by Readless", url: "https://www.readless.app/blog/feedly-pro-pricing-vs-readless-2026" },
          { label: "Feedly Free, Pro and Pro+ explained, checked Oct 13, 2026", url: "https://bestsocialmediascheduler.com/reviews/feedly" },
          { label: "Feedly pricing page", url: "https://feedly.com/i/pro" },
        ],
      }}
    />
  );
}
