"use client";
/**
 * Landing / marketing page.
 *
 * Logged-in users are routed to /digest; logged-out visitors see the value
 * proposition + pricing. This replaces the old bare redirect so the product
 * has a real front door for the launch (HN, r/rss, r/selfhosted).
 */
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
    features: [
      "30 sources, 5 creators",
      "Full ranking engine",
      "Once-daily digest",
      "Self-hostable",
    ],
    cta: "Get started",
    href: "/register",
    highlight: false,
  },
  {
    name: "Pro",
    price: "$4.99",
    cadence: "/month",
    features: [
      "Unlimited sources, 50 creators",
      "Cross-source synthesis",
      "Serendipity controls",
      "Up to 4× daily digests",
    ],
    cta: "Start Pro",
    href: "/register",
    highlight: true,
  },
  {
    name: "Self-hosted",
    price: "Free",
    cadence: "open source",
    features: [
      "Unlimited everything",
      "Bring your own LLM key",
      "Full ranking engine",
      "Docker Compose one-command",
    ],
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
    <div style={{ fontFamily: "inherit" }}>
      {/* Nav */}
      <nav
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 24px",
          borderBottom: "1px solid #e5e7eb",
          background: "#fff",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <span style={{ fontWeight: 800, fontSize: "1.15rem", color: "#1d4ed8" }}>
          ◭ ReadPrism
        </span>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <a href="#pricing" style={{ color: "#374151", textDecoration: "none", fontSize: 14 }}>
            Pricing
          </a>
          <a href="/login" style={{ color: "#374151", textDecoration: "none", fontSize: 14 }}>
            Sign in
          </a>
          <a
            href="/register"
            style={{
              background: "#2563eb",
              color: "#fff",
              padding: "8px 16px",
              borderRadius: 6,
              textDecoration: "none",
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            Get started
          </a>
        </div>
      </nav>

      {/* Hero */}
      <header
        style={{
          maxWidth: 880,
          margin: "0 auto",
          padding: "72px 24px 48px",
          textAlign: "center",
        }}
      >
        <h1 style={{ fontSize: "2.6rem", fontWeight: 800, lineHeight: 1.1, margin: "0 0 20px", letterSpacing: "-0.02em" }}>
          Your sources, your creators —
          <br />
          <span style={{ color: "#1d4ed8" }}>ranked for you.</span>
        </h1>
        <p style={{ fontSize: "1.15rem", color: "#4b5563", lineHeight: 1.6, margin: "0 auto 32px", maxWidth: 640 }}>
          ReadPrism aggregates everything you follow and ranks it by personal
          relevance — not chronology, not popularity. A learning engine that
          gets sharper the more you read.
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
          <a
            href="/register"
            style={{
              background: "#2563eb",
              color: "#fff",
              padding: "12px 28px",
              borderRadius: 8,
              textDecoration: "none",
              fontWeight: 600,
              fontSize: 15,
            }}
          >
            Start reading smarter
          </a>
          <a
            href="#how"
            style={{
              background: "#fff",
              color: "#374151",
              padding: "12px 28px",
              borderRadius: 8,
              textDecoration: "none",
              fontWeight: 600,
              fontSize: 15,
              border: "1px solid #d1d5db",
            }}
          >
            How it works
          </a>
        </div>
        <p style={{ color: "#9ca3af", fontSize: 13, marginTop: 16 }}>
          Free tier · Self-hostable · Open source
        </p>
      </header>

      {/* The problem */}
      <section style={{ background: "#f9fafb", padding: "64px 24px" }}>
        <div style={{ maxWidth: 720, margin: "0 auto", textAlign: "center" }}>
          <h2 style={{ fontSize: "1.6rem", fontWeight: 700, marginBottom: 16 }}>
            Following 80 sources means triaging 200 items a day.
          </h2>
          <p style={{ fontSize: "1.05rem", color: "#4b5563", lineHeight: 1.7 }}>
            A chronological feed of 200 items isn&apos;t a solution — it&apos;s a
            different kind of noise. Even filtering by topic leaves 60. What you
            actually need is a <strong>ranked</strong> list: ordered by the
            probability that <em>this</em> item is worth <em>your</em> attention,
            right now.
          </p>
        </div>
      </section>

      {/* How it works */}
      <section id="how" style={{ padding: "64px 24px", maxWidth: 960, margin: "0 auto" }}>
        <h2 style={{ fontSize: "1.6rem", fontWeight: 700, textAlign: "center", marginBottom: 8 }}>
          Eight signals. One score. Yours.
        </h2>
        <p style={{ textAlign: "center", color: "#6b7280", marginBottom: 40 }}>
          The Personalized Relevance Score is a weighted composite — and the
          weights are learned per user.
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: 16,
          }}
        >
          {SIGNALS.map(([title, desc]) => (
            <div
              key={title}
              style={{
                padding: 20,
                border: "1px solid #e5e7eb",
                borderRadius: 10,
                background: "#fff",
              }}
            >
              <h3 style={{ fontSize: "1rem", fontWeight: 600, margin: "0 0 6px", color: "#1d4ed8" }}>
                {title}
              </h3>
              <p style={{ fontSize: "0.9rem", color: "#4b5563", lineHeight: 1.5, margin: 0 }}>
                {desc}
              </p>
            </div>
          ))}
        </div>
        <p style={{ textAlign: "center", color: "#6b7280", marginTop: 32, fontSize: 14 }}>
          Tap <em>“Why this?”</em> on any item to see exactly which signals drove its ranking —
          and how strongly.
        </p>
      </section>

      {/* Pricing */}
      <section id="pricing" style={{ background: "#f9fafb", padding: "64px 24px" }}>
        <div style={{ maxWidth: 960, margin: "0 auto" }}>
          <h2 style={{ fontSize: "1.6rem", fontWeight: 700, textAlign: "center", marginBottom: 8 }}>
            Pricing
          </h2>
          <p style={{ textAlign: "center", color: "#6b7280", marginBottom: 40 }}>
            The full ranking engine is free. Paid tiers add scale and convenience.
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: 20,
              alignItems: "stretch",
            }}
          >
            {PRICING.map((tier) => (
              <div
                key={tier.name}
                style={{
                  padding: 28,
                  borderRadius: 12,
                  background: tier.highlight ? "#1d4ed8" : "#fff",
                  color: tier.highlight ? "#fff" : "#1f2937",
                  border: tier.highlight ? "none" : "1px solid #e5e7eb",
                  boxShadow: tier.highlight ? "0 8px 24px rgba(29,78,216,0.2)" : "none",
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 8px" }}>
                  {tier.name}
                </h3>
                <div style={{ marginBottom: 20 }}>
                  <span style={{ fontSize: "2rem", fontWeight: 800 }}>{tier.price}</span>
                  <span style={{ opacity: 0.7, fontSize: 14 }}> {tier.cadence}</span>
                </div>
                <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", fontSize: 14, lineHeight: 1.9, flex: 1 }}>
                  {tier.features.map((f) => (
                    <li key={f}>✓ {f}</li>
                  ))}
                </ul>
                <a
                  href={tier.href}
                  style={{
                    display: "block",
                    textAlign: "center",
                    padding: "10px",
                    borderRadius: 8,
                    textDecoration: "none",
                    fontWeight: 600,
                    fontSize: 14,
                    background: tier.highlight ? "#fff" : "#2563eb",
                    color: tier.highlight ? "#1d4ed8" : "#fff",
                  }}
                >
                  {tier.cta}
                </a>
              </div>
            ))}
          </div>
          <p style={{ textAlign: "center", color: "#9ca3af", marginTop: 24, fontSize: 13 }}>
            Pro at $4.99/mo undercuts Feedly Pro+ ($12.99) and Readwise Reader ($9.99).
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ padding: "32px 24px", textAlign: "center", color: "#9ca3af", fontSize: 13 }}>
        <p>ReadPrism — relevance is a relationship, not a property of content.</p>
      </footer>
    </div>
  );
}
