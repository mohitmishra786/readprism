import type { Metadata } from "next";
import { ComparisonPage } from "../../../components/marketing/ComparisonPage";

export const metadata: Metadata = {
  title: "ReadPrism vs Feedly — behavioral ranking vs keyword rules",
  description:
    "How ReadPrism compares to Feedly: behavioral, explainable ranking that learns from how you actually read vs Feedly Leo's keyword/topic rules. Open source and self-hostable.",
  alternates: { canonical: "/vs/feedly" },
};

export default function VsFeedly() {
  return (
    <ComparisonPage
      data={{
        competitor: "Feedly",
        intro:
          "Feedly is the incumbent RSS reader; its Leo AI trains by keyword and topic rules you maintain. ReadPrism ranks by your actual reading behavior and explains every ranking.",
        rows: [
          { dimension: "Ranking basis", competitor: "Leo: keyword/topic rules, train-by-example (Pro+)", readprism: "8 behavioral signals + per-user learned weights" },
          { dimension: "Explainability", competitor: "Prioritization, limited reasoning", readprism: "Per-item why-ranked + named interest-graph connections" },
          { dimension: "Pricing", competitor: "Free / Pro $6.99 / Pro+ ~$99/yr", readprism: "Full engine free; $4.99/mo Pro (planned)" },
          { dimension: "Self-hosting", competitor: "No", readprism: "Yes — Docker Compose, MIT-licensed" },
        ],
        differsBecause: [
          "Behavioral, not keyword: ReadPrism learns from scroll depth and active reading time, not rules you maintain by hand.",
          "Explainable: every item shows the signals that drove it and, when relevant, the topic connection.",
          "Open and self-hostable: the full ranking engine is free and the code is yours to run.",
        ],
        fairnote:
          "Feedly is a mature product with broad integrations and a large free tier; ReadPrism is earlier and narrower, focused on the behavioral-ranking wedge.",
      }}
    />
  );
}
