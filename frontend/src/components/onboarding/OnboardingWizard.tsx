"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { InterestInput } from "./InterestInput";
import { SampleArticles, type SampleRating } from "./SampleArticles";
import { api } from "../../lib/api";

const STEPS = ["Interests", "Confirm Topics", "Sample Articles", "Add Sources", "Add Creators", "Digest Preferences"];

export function OnboardingWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [interestText, setInterestText] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [topicInput, setTopicInput] = useState("");
  const [expanding, setExpanding] = useState(false);
  const [sampleRatings, setSampleRatings] = useState<SampleRating[]>([]);
  const [sourceUrl, setSourceUrl] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [creatorInput, setCreatorInput] = useState("");
  const [digestFreq, setDigestFreq] = useState("daily");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  // Step 0 -> 1 runs interest expansion (LLM with keyword fallback) so the
  // user confirms/edits the subtopics that become their initial clusters.
  const expandAndContinue = async () => {
    if (!interestText.trim()) {
      setError("Tell us a little about what you read first.");
      return;
    }
    setError("");
    setExpanding(true);
    try {
      const { topics: found } = await api.onboarding.expandInterests(interestText.trim());
      setTopics(found);
      setStep(1);
    } catch {
      // Expansion is optional polish: continue with no confirmed topics and
      // let the backend extract from the raw text.
      setTopics([]);
      setStep(1);
    } finally {
      setExpanding(false);
    }
  };

  const addTopic = () => {
    const t = topicInput.trim();
    if (t && !topics.includes(t)) setTopics((prev) => [...prev, t]);
    setTopicInput("");
  };

  const addSource = () => {
    if (sourceUrl.trim()) {
      setSources((prev) => [...prev, sourceUrl.trim()]);
      setSourceUrl("");
    }
  };

  const finish = async () => {
    setLoading(true);
    setError("");
    try {
      // 1. Submit interest text and sample ratings to the onboarding endpoint
      await api.onboarding.complete({
        interest_text: interestText,
        sample_ratings: sampleRatings.map((r) => ({
          article_url: r.article_url,
          title: r.title,
          rating: r.rating,
        })),
        source_opml: null,
        confirmed_topics: topics.length > 0 ? topics : undefined,
      });

      // 2. Add sources and creator via their APIs
      for (const url of sources) {
        await api.sources.add(url).catch(() => {});
      }
      if (creatorInput.trim()) {
        await api.creators.add(creatorInput.trim()).catch(() => {});
      }

      // 3. Update preferences
      await api.preferences.update({ digest_frequency: digestFreq });

      // 4. Trigger first digest
      await api.digest.generate().catch(() => {});

      router.replace("/digest");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: "40px auto", padding: "0 16px" }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: 4 }}>
          Welcome to ReadPrism
        </h1>
        <p style={{ color: "var(--text-tertiary)" }}>
          Step {step + 1} of {STEPS.length}: {STEPS[step]}
        </p>
        <div style={{ display: "flex", gap: 4, marginTop: 12 }}>
          {STEPS.map((_, i) => (
            <div
              key={i}
              style={{
                height: 4,
                flex: 1,
                borderRadius: 2,
                background: i <= step ? "#2563eb" : "#e5e7eb",
              }}
            />
          ))}
        </div>
      </div>

      {step === 0 && (
        <InterestInput value={interestText} onChange={setInterestText} />
      )}

      {step === 1 && (
        <div>
          <p style={{ color: "var(--text-tertiary)", marginBottom: 16 }}>
            We expanded your interests into these topics. They seed your first
            digest — remove any that are wrong and add what&apos;s missing.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
            {topics.map((t) => (
              <span
                key={t}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 12px",
                  borderRadius: 16,
                  background: "rgba(37,99,235,0.12)",
                  color: "#1e40af",
                  fontSize: 14,
                }}
              >
                {t}
                <button
                  onClick={() => setTopics((prev) => prev.filter((x) => x !== t))}
                  aria-label={`Remove topic ${t}`}
                  style={{ background: "none", border: "none", color: "#1e40af", cursor: "pointer", padding: 0 }}
                >
                  ✕
                </button>
              </span>
            ))}
            {topics.length === 0 && (
              <p style={{ fontSize: 14 }}>
                No topics extracted — add a few yourself below.
              </p>
            )}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={topicInput}
              onChange={(e) => setTopicInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addTopic()}
              placeholder="Add a topic…"
              aria-label="Add a topic"
              style={{ flex: 1, padding: "8px 12px", border: "1px solid var(--border-strong)", borderRadius: 6 }}
            />
            <button
              onClick={addTopic}
              style={{ padding: "8px 16px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}
            >
              Add
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <SampleArticles ratings={sampleRatings} onRate={setSampleRatings} />
      )}

      {step === 3 && (
        <div>
          <p style={{ color: "var(--text-tertiary)", marginBottom: 16 }}>
            Add websites or RSS feeds you follow.{" "}
            <strong>Optional</strong> — we’ll seed starter sources from your
            interests, and you can add your own anytime.
          </p>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addSource()}
              placeholder="https://example.com/blog"
              style={{ flex: 1, padding: "8px 12px", border: "1px solid var(--border-strong)", borderRadius: 6 }}
            />
            <button
              onClick={addSource}
              style={{ padding: "8px 16px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}
            >
              Add
            </button>
          </div>
          {sources.map((s) => (
            <div key={s} style={{ padding: "6px 12px", background: "var(--bg-sunken)", borderRadius: 6, marginBottom: 6, fontSize: 14 }}>
              {s}
            </div>
          ))}
        </div>
      )}

      {step === 4 && (
        <div>
          <p style={{ color: "var(--text-tertiary)", marginBottom: 16 }}>
            Add creators you follow (name or URL). <strong>Optional</strong> —
            skip and add later from the Creators page.
          </p>
          <input
            type="text"
            value={creatorInput}
            onChange={(e) => setCreatorInput(e.target.value)}
            placeholder="https://simonwillison.substack.com or Simon Willison"
            style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border-strong)", borderRadius: 6 }}
          />
        </div>
      )}

      {step === 5 && (
        <div>
          <label style={{ display: "block", fontWeight: 500, marginBottom: 8 }}>Digest frequency</label>
          <select
            value={digestFreq}
            onChange={(e) => setDigestFreq(e.target.value)}
            style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border-strong)", borderRadius: 6 }}
          >
            <option value="daily">Daily</option>
            <option value="twice_daily">Twice daily</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>
      )}

      {error && <p style={{ color: "#ef4444", marginTop: 16 }}>{error}</p>}

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 32 }}>
        <button
          onClick={back}
          disabled={step === 0}
          style={{
            padding: "10px 20px",
            border: "1px solid var(--border-strong)",
            borderRadius: 6,
            background: "var(--bg-elevated)",
            cursor: step === 0 ? "not-allowed" : "pointer",
            opacity: step === 0 ? 0.4 : 1,
          }}
        >
          Back
        </button>
        {step < STEPS.length - 1 ? (
          <button
            onClick={step === 0 ? expandAndContinue : next}
            disabled={expanding}
            style={{
              padding: "10px 20px",
              background: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              cursor: expanding ? "not-allowed" : "pointer",
              opacity: expanding ? 0.7 : 1,
            }}
          >
            {expanding
              ? "Finding your topics…"
              : /* Optional steps (sources/creators) read as "Skip" when empty */
                (step === 3 && sources.length === 0) || (step === 4 && !creatorInput)
                ? "Skip for now"
                : "Continue"}
          </button>
        ) : (
          <button
            onClick={finish}
            disabled={loading}
            style={{
              padding: "10px 20px",
              background: "#059669",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Setting up..." : "Start ReadPrism"}
          </button>
        )}
      </div>
    </div>
  );
}
