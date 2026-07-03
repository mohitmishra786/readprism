"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "../lib/auth";

const SIGNALS = [
  ["Semantic alignment", "Matches the meaning of what you read, not just keywords."],
  ["Reading depth", "Learns from how far you actually read — scroll depth and active time."],
  ["Source trust", "Trust weights learned per source and per creator-topic intersection."],
  ["Temporal context", "Long-term interests, medium-term focus, and session saturation."],
  ["Suggestion signal", "The purest signal: what you read from sources you didn't follow."],
  ["Serendipity layer", "A configurable slice reserved for genuine discovery."],
] as const;

const PRICING = [
  {
    name: "Free",
    price: "$0",
    cadence: "forever",
    features: ["30 sources, 5 creators", "Full ranking engine", "Once-daily digest", "Self-hostable"],
    cta: "Get started",
    href: "/register",
    highlight: false,
  },
  {
    name: "Pro",
    price: "$4.99",
    cadence: "/month",
    features: ["Unlimited sources, 50 creators", "Cross-source synthesis", "Serendipity controls", "Up to 4× daily digests"],
    cta: "Start Pro",
    href: "/register",
    highlight: true,
  },
  {
    name: "Self-hosted",
    price: "Free",
    cadence: "open source",
    features: ["Unlimited everything", "Bring your own LLM key", "Full ranking engine", "Docker Compose one-command"],
    cta: "Self-host",
    href: "https://github.com/readprism/readprism",
    highlight: false,
  },
];

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated()) router.replace("/digest");
  }, [router]);

  return (
    <div className="min-h-screen bg-stone-50">
      {/* Nav */}
      <nav className="sticky top-0 z-40 border-b border-stone-200 bg-white/80 backdrop-blur-lg">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <span className="prism-mark text-lg">◭ ReadPrism</span>
          <div className="flex items-center gap-4">
            <a href="#pricing" className="text-sm text-stone-600 hover:text-stone-900">
              Pricing
            </a>
            <a href="/login" className="text-sm text-stone-600 hover:text-stone-900">
              Sign in
            </a>
            <a href="/register" className="btn-primary text-sm">
              Get started
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <header className="mx-auto max-w-3xl px-4 py-20 text-center md:py-28">
        <div className="eyebrow mb-4 text-prism-700">Personalized Content Intelligence</div>
        <h1 className="font-serif text-5xl font-bold leading-[1.05] tracking-tight text-stone-900 md:text-6xl">
          Your sources, your creators —{" "}
          <span className="prism-mark">ranked for you.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-stone-600">
          ReadPrism aggregates everything you follow and ranks it by personal
          relevance — not chronology, not popularity. A learning engine that gets
          sharper the more you read.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <a href="/register" className="btn-primary px-7 py-3 text-base">
            Start reading smarter
          </a>
          <a href="#how" className="btn-secondary px-7 py-3 text-base">
            How it works
          </a>
        </div>
        <p className="mt-4 text-xs text-stone-400">
          Free tier · Self-hostable · Open source
        </p>
      </header>

      {/* The problem */}
      <section className="border-y border-stone-200 bg-white py-20">
        <div className="mx-auto max-w-2xl px-4 text-center">
          <h2 className="font-serif text-3xl font-bold text-stone-900">
            Following 80 sources means triaging 200 items a day.
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-stone-600">
            A chronological feed of 200 items isn&apos;t a solution — it&apos;s a
            different kind of noise. What you actually need is a{" "}
            <strong className="text-stone-900">ranked</strong> list: ordered by the
            probability that <em>this</em> item is worth <em>your</em> attention,
            right now.
          </p>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="mx-auto max-w-5xl px-4 py-20">
        <div className="text-center">
          <h2 className="font-serif text-3xl font-bold text-stone-900">
            Eight signals. One score. Yours.
          </h2>
          <p className="mt-3 text-stone-500">
            The Personalized Relevance Score is a weighted composite — and the
            weights are learned per user.
          </p>
        </div>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SIGNALS.map(([title, desc]) => (
            <div key={title} className="card card-hover p-5">
              <h3 className="text-sm font-semibold text-prism-700">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-stone-600">{desc}</p>
            </div>
          ))}
        </div>
        <p className="mt-10 text-center text-sm text-stone-500">
          Tap <em>“Why this?”</em> on any item to see exactly which signals drove its
          ranking — and how strongly.
        </p>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-t border-stone-200 bg-white py-20">
        <div className="mx-auto max-w-5xl px-4">
          <div className="text-center">
            <h2 className="font-serif text-3xl font-bold text-stone-900">Pricing</h2>
            <p className="mt-3 text-stone-500">
              The full ranking engine is free. Paid tiers add scale and convenience.
            </p>
          </div>
          <div className="mt-12 grid items-stretch gap-5 md:grid-cols-3">
            {PRICING.map((tier) => (
              <div
                key={tier.name}
                className={`card flex flex-col p-7 ${
                  tier.highlight
                    ? "border-transparent bg-stone-900 text-white shadow-xl"
                    : ""
                }`}
              >
                <h3 className={`text-lg font-bold ${tier.highlight ? "text-white" : "text-stone-900"}`}>
                  {tier.name}
                </h3>
                <div className="mt-3 mb-6">
                  <span className="font-serif text-4xl font-bold">{tier.price}</span>
                  <span className={`text-sm ${tier.highlight ? "text-stone-400" : "text-stone-500"}`}>
                    {" "}
                    {tier.cadence}
                  </span>
                </div>
                <ul className={`mb-8 flex-1 space-y-2 text-sm ${tier.highlight ? "text-stone-300" : "text-stone-600"}`}>
                  {tier.features.map((f) => (
                    <li key={f}>✓ {f}</li>
                  ))}
                </ul>
                <a
                  href={tier.href}
                  className={`btn w-full py-2.5 text-sm font-semibold ${
                    tier.highlight ? "bg-white text-stone-900 hover:bg-stone-100" : "btn-primary"
                  }`}
                >
                  {tier.cta}
                </a>
              </div>
            ))}
          </div>
          <p className="mt-8 text-center text-xs text-stone-400">
            Pro at $4.99/mo undercuts Feedly Pro+ ($12.99) and Readwise Reader ($9.99).
          </p>
        </div>
      </section>

      <footer className="py-12 text-center text-sm text-stone-400">
        ReadPrism — relevance is a relationship, not a property of content.
      </footer>
    </div>
  );
}
