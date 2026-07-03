"use client";
import { useEffect, useState } from "react";
import type { Digest, DigestItem } from "../../lib/types";
import { DigestSection } from "./DigestSection";
import { api } from "../../lib/api";

const SECTION_ORDER = ["lead", "creator", "deep_reads", "discovery"];

interface Prompt {
  id: string;
  prompt_text: string;
  prompt_type: string;
  answered: boolean;
  answer: string | null;
}

function FeedbackPrompts({ digestId }: { digestId: string }) {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  useEffect(() => {
    api.digest.prompts(digestId).then(setPrompts).catch(() => {});
  }, [digestId]);

  const submit = async (promptId: string) => {
    const answer = answers[promptId]?.trim();
    if (!answer) return;
    try {
      await api.digest.answerPrompt(digestId, promptId, answer);
      setPrompts((prev) =>
        prev.map((p) => (p.id === promptId ? { ...p, answered: true, answer } : p))
      );
    } catch {}
  };

  const unanswered = prompts.filter((p) => !p.answered);
  if (unanswered.length === 0) return null;

  return (
    <div
      style={{
        background: "#eff6ff",
        border: "1px solid #bfdbfe",
        borderRadius: 8,
        padding: 16,
        marginBottom: 24,
      }}
    >
      <p style={{ fontWeight: 600, marginBottom: 12, fontSize: "0.9rem", color: "#1e40af" }}>
        Help us calibrate your feed
      </p>
      {unanswered.map((p) => (
        <div key={p.id} style={{ marginBottom: 12 }}>
          <p style={{ fontSize: "0.9rem", marginBottom: 6, color: "#1f2937" }}>{p.prompt_text}</p>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={answers[p.id] || ""}
              onChange={(e) => setAnswers((prev) => ({ ...prev, [p.id]: e.target.value }))}
              onKeyDown={(e) => e.key === "Enter" && submit(p.id)}
              placeholder="Your answer..."
              style={{ flex: 1, padding: "6px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13 }}
            />
            <button
              onClick={() => submit(p.id)}
              style={{
                padding: "6px 14px",
                background: "#2563eb",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              Send
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

interface DigestViewProps {
  digest: Digest;
  /** Optional: account creation date, used to show a one-time "how ranking
   * works" banner for new users. ISO string. */
  userCreatedAt?: string;
}

const SECTION_HEADERS: Record<string, string> = {
  lead: "Lead — what matters most today",
  creator: "From creators you follow",
  deep_reads: "Deep reads",
  discovery: "Discovery — outside your usual sources",
};

function FirstDigestBanner({ onDismiss }: { onDismiss: () => void }) {
  // One-time explanation for new users: the digest is ranked, not chronological,
  // and it learns from how you read. This makes the sophistication legible and
  // sets the expectation that the digest improves over the first few weeks.
  return (
    <div
      style={{
        background: "linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%)",
        border: "1px solid #bfdbfe",
        borderRadius: 8,
        padding: 16,
        marginBottom: 24,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <p
          style={{
            fontWeight: 600,
            marginBottom: 8,
            fontSize: "0.9rem",
            color: "#1e40af",
          }}
        >
          👋 Your first digest
        </p>
        <button
          onClick={onDismiss}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "#6b7280",
            fontSize: 16,
            lineHeight: 1,
            padding: 0,
          }}
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
      <p style={{ fontSize: "0.875rem", lineHeight: 1.6, color: "#1e3a8a", margin: 0 }}>
        Items below are <strong>ranked by personal relevance</strong>, not chronological.
        The ranking learns from what you read fully, what you skip, and what you rate —
        so it gets noticeably sharper over the next few weeks. Tap{" "}
        <em>“Why this?”</em> on any item to see why it ranked where it did.
      </p>
    </div>
  );
}

export function DigestView({ digest, userCreatedAt }: DigestViewProps) {
  const [showFirstDigest, setShowFirstDigest] = useState(true);

  const grouped = SECTION_ORDER.reduce<Record<string, DigestItem[]>>((acc, s) => {
    acc[s] = digest.items.filter((i) => i.section === s);
    return acc;
  }, {});

  // Show the new-user banner only for accounts younger than 14 days.
  const isNewUser =
    userCreatedAt &&
    Date.now() - new Date(userCreatedAt).getTime() < 14 * 24 * 60 * 60 * 1000;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: 4 }}>
          Your Digest
        </h1>
        <p style={{ color: "#6b7280", fontSize: "0.9rem" }}>
          {new Date(digest.generated_at).toLocaleDateString("en-US", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}{" "}
          · {digest.total_items} items
        </p>
      </div>

      {isNewUser && showFirstDigest && (
        <FirstDigestBanner onDismiss={() => setShowFirstDigest(false)} />
      )}

      <FeedbackPrompts digestId={digest.id} />

      {SECTION_ORDER.map((section) => (
        <DigestSection
          key={section}
          name={section}
          items={grouped[section] || []}
        />
      ))}
    </div>
  );
}
