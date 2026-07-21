import type { Metadata } from "next";
import { MarketingShell } from "../../components/marketing/MarketingShell";

export const metadata: Metadata = {
  title: "How ReadPrism ranks your reading: 8 signals + per-user gradient descent",
  description:
    "A transparent look at ReadPrism's ranking engine — eight behavioral signals, per-user learned weights via gradient descent, and a decaying interest graph with transitive relevance.",
  alternates: { canonical: "/how-it-works" },
};

export default function HowItWorks() {
  return (
    <MarketingShell>
      <article className="prose-reader">
        <h1 className="font-serif text-3xl font-bold">
          How ReadPrism ranks your reading
        </h1>
        <p className="mt-4 text-lg text-stone-600 dark:text-stone-300">
          Relevance is a relationship between content, a specific person, and
          time — not a property of content alone. ReadPrism computes a{" "}
          <strong>Personalized Relevance Score (PRS)</strong> per item, per user,
          from eight signals, then learns how to weight them from how you actually
          read.
        </p>

        <h2 className="mt-8 font-serif text-2xl font-semibold">The eight signals</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-6">
          <li>
            <strong>Semantic alignment</strong> — cosine similarity between the
            article and your interest clusters (per-cluster max, so a
            cooking-plus-compilers reader isn&apos;t averaged into a blur), plus
            transitive &quot;bridge&quot; vectors for the intersection of two
            connected interests.
          </li>
          <li>
            <strong>Reading depth</strong> — real scroll depth and active reading
            time from the in-app reader, not clicks.
          </li>
          <li>
            <strong>Suggestion signal</strong> — what you read from sources you
            didn&apos;t follow (the purest signal that discovery is working).
          </li>
          <li>
            <strong>Explicit feedback</strong> — thumbs, tagged reasons, saves.
          </li>
          <li>
            <strong>Source &amp; creator trust</strong> — learned per source, and
            even per creator-per-topic.
          </li>
          <li>
            <strong>Content quality</strong> — length, citations, originality
            heuristics.
          </li>
          <li>
            <strong>Temporal context</strong> — long-term interests, medium-term
            focus, and session saturation.
          </li>
          <li>
            <strong>Novelty</strong> — a configurable serendipity band for
            discovery outside your established clusters.
          </li>
        </ol>

        <h2 className="mt-8 font-serif text-2xl font-semibold">
          Per-user learned weights
        </h2>
        <p className="mt-3">
          The weights are learned per user via single-layer gradient descent on
          prediction accuracy — so the engine gets sharper the more you read.
          Signals that are themselves derived from the engagement target (reading
          depth, explicit feedback) are held out of the regression so the model
          can&apos;t inflate them by predicting its own inputs.
        </p>

        <h2 className="mt-8 font-serif text-2xl font-semibold">
          Explainable, not a black box
        </h2>
        <p className="mt-3">
          Every item shows why it ranked — the contributing signals and, when a
          graph connection drove it, the named topics (&quot;connects your
          interest in compilers and language design&quot;). You can validate the
          claim yourself: <code>scripts/ranking_eval.py</code> reports
          read-prediction AUC per cohort.
        </p>

        <h2 className="mt-8 font-serif text-2xl font-semibold">Open and honest</h2>
        <p className="mt-3">
          The full ranking engine is free, the code is open source and
          self-hostable (Docker Compose), and platforms without a public feed
          (Twitter/X, LinkedIn) are marked unsupported rather than silently
          failing.
        </p>
        <p className="mt-6">
          <a href="/register" className="text-prism-700 underline">
            Try it →
          </a>
        </p>
      </article>
    </MarketingShell>
  );
}
