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
        prev.map((p) => (p.id === promptId ? { ...p, answered: true, answer } : p)),
      );
    } catch {}
  };

  const unanswered = prompts.filter((p) => !p.answered);
  if (unanswered.length === 0) return null;

  return (
    <div className="mb-8 rounded-xl border border-prism-200 bg-prism-50 p-5">
      <p className="mb-3 text-sm font-semibold text-prism-800">
        Help us calibrate your feed
      </p>
      {unanswered.map((p) => (
        <div key={p.id} className="mb-3 last:mb-0">
          <p className="mb-2 text-sm text-stone-700">{p.prompt_text}</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={answers[p.id] || ""}
              onChange={(e) => setAnswers((prev) => ({ ...prev, [p.id]: e.target.value }))}
              onKeyDown={(e) => e.key === "Enter" && submit(p.id)}
              placeholder="Your answer..."
              className="input flex-1"
            />
            <button onClick={() => submit(p.id)} className="btn-primary">
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
  userCreatedAt?: string;
}

function FirstDigestBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="mb-8 overflow-hidden rounded-xl border border-prism-200 bg-gradient-to-br from-prism-50 to-cyan-50 p-5">
      <div className="flex items-start justify-between">
        <p className="mb-2 text-sm font-semibold text-prism-800">
          👋 Your first digest
        </p>
        <button
          onClick={onDismiss}
          className="text-stone-400 transition-colors hover:text-stone-700"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
      <p className="text-sm leading-relaxed text-prism-900/80">
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

  const isNewUser =
    userCreatedAt &&
    Date.now() - new Date(userCreatedAt).getTime() < 14 * 24 * 60 * 60 * 1000;

  return (
    <div className="animate-fade-in">
      <header className="mb-8 border-b border-stone-200 pb-6">
        <div className="eyebrow text-prism-700">Your Daily Edition</div>
        <h1 className="mt-1 font-serif text-4xl font-bold tracking-tight text-stone-900">
          Your Digest
        </h1>
        <p className="mt-2 text-sm text-stone-500">
          {new Date(digest.generated_at).toLocaleDateString("en-US", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
          })}{" "}
          · {digest.total_items} items
        </p>
      </header>

      {isNewUser && showFirstDigest && (
        <FirstDigestBanner onDismiss={() => setShowFirstDigest(false)} />
      )}

      <FeedbackPrompts digestId={digest.id} />

      {SECTION_ORDER.map((section) => (
        <DigestSection key={section} name={section} items={grouped[section] || []} />
      ))}
    </div>
  );
}
