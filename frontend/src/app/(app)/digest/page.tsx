"use client";
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";
import type { Digest } from "../../../lib/types";
import { DigestView } from "../../../components/digest/DigestView";
import { OnboardingWizard } from "../../../components/onboarding/OnboardingWizard";

export default function DigestPage() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    loadDigest();
  }, []);

  const loadDigest = async () => {
    setLoading(true);
    try {
      const user = await api.auth.me();
      if (!user.onboarding_complete) {
        setNeedsOnboarding(true);
        setLoading(false);
        return;
      }
      const d = await api.digest.latest();
      setDigest(d);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("404") || msg.includes("No digest")) {
        setError("no_digest");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const generateDigest = async () => {
    setGenerating(true);
    try {
      await api.digest.generate();
      // Poll for digest
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const d = await api.digest.latest();
          setDigest(d);
          setError("");
          clearInterval(poll);
          setGenerating(false);
        } catch {}
        if (attempts > 30) {
          clearInterval(poll);
          setGenerating(false);
          setError("Digest generation is taking longer than expected. Try refreshing.");
        }
      }, 3000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to generate digest");
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 60, color: "#6b7280" }}>
        Loading your digest...
      </div>
    );
  }

  if (needsOnboarding) {
    return <OnboardingWizard />;
  }

  if (error === "no_digest") {
    return (
      <div style={{ textAlign: "center", padding: 60 }}>
        <h2 style={{ marginBottom: 16 }}>No digest yet</h2>
        <p style={{ color: "#6b7280", marginBottom: 24 }}>
          Generate your first personalized digest.
        </p>
        <button
          onClick={generateDigest}
          disabled={generating}
          style={{
            padding: "12px 24px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            fontSize: "1rem",
            cursor: generating ? "not-allowed" : "pointer",
            opacity: generating ? 0.7 : 1,
          }}
        >
          {generating ? "Generating..." : "Generate Digest"}
        </button>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: "center", padding: 60, color: "#ef4444" }}>
        Error: {error}
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <button
          onClick={generateDigest}
          disabled={generating}
          style={{
            padding: "8px 16px",
            background: "#fff",
            border: "1px solid #d1d5db",
            borderRadius: 6,
            cursor: generating ? "not-allowed" : "pointer",
            fontSize: 14,
            opacity: generating ? 0.7 : 1,
          }}
        >
          {generating ? "Generating..." : "Refresh digest"}
        </button>
      </div>
      {digest && <DigestView digest={digest} />}
    </div>
  );
}
