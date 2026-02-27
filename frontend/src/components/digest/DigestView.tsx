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
}

export function DigestView({ digest }: DigestViewProps) {
  const grouped = SECTION_ORDER.reduce<Record<string, DigestItem[]>>((acc, s) => {
    acc[s] = digest.items.filter((i) => i.section === s);
    return acc;
  }, {});

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
