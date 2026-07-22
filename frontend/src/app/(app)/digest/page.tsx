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
  const [userCreatedAt, setUserCreatedAt] = useState<string | undefined>(undefined);

  useEffect(() => {
    loadDigest();
  }, []);

  const loadDigest = async () => {
    setLoading(true);
    try {
      const user = await api.auth.me();
      setUserCreatedAt(user.created_at);
      if (!user.onboarding_complete) {
        setNeedsOnboarding(true);
        setLoading(false);
        return;
      }
      const d = await api.digest.latest();
      setDigest(d);
    } catch (err: unknown) {
      // 404 means no digest yet — that's a valid state, not an error.
      setError("");
    } finally {
      setLoading(false);
    }
  };

  const generate = async () => {
    setGenerating(true);
    setError("");
    try {
      await api.digest.generate();
      // Poll for the digest to appear (worker builds it async).
      for (let i = 0; i < 12; i++) {
        await new Promise((r) => setTimeout(r, 4000));
        try {
          const d = await api.digest.latest();
          if (d) {
            setDigest(d);
            setGenerating(false);
            return;
          }
        } catch {}
      }
      setGenerating(false);
      setError("Digest is still building — refresh in a moment.");
    } catch (err: unknown) {
      setGenerating(false);
      setError(err instanceof Error ? err.message : "Failed to generate digest");
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-10 w-48 rounded" />
        <div className="skeleton h-4 w-32 rounded" />
        <div className="mt-8 space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-5">
              <div className="skeleton mb-3 h-5 w-3/4 rounded" />
              <div className="skeleton mb-2 h-3 w-full rounded" />
              <div className="skeleton h-3 w-5/6 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (needsOnboarding) {
    return <OnboardingWizard />;
  }

  // First-run honest state (audit 10-1): a brand-new user's sources haven't been
  // ingested + embedded yet (feeds run on a schedule), so ranking is meaningless.
  // Show an honest "gathering" screen instead of an empty/near-random digest at
  // the exact make-or-break moment.
  const isNewUser =
    userCreatedAt != null &&
    Date.now() - new Date(userCreatedAt).getTime() < 6 * 60 * 60 * 1000;
  const digestIsEmpty = !digest || digest.total_items === 0;
  if (isNewUser && digestIsEmpty && !generating) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="relative mb-6 h-12 w-12">
          <div className="absolute inset-0 animate-spin rounded-full border-2 border-stone-200 border-t-prism-600" />
        </div>
        <h2 className="font-serif text-2xl font-bold text-stone-900">
          Gathering your first reads
        </h2>
        <p className="mt-2 max-w-md text-sm text-stone-500">
          We’re fetching and reading through your sources now. Your first ranked
          digest gets noticeably sharper as real articles come in — check back in
          a little while, or try building one from what we have so far.
        </p>
        <button
          onClick={generate}
          disabled={generating}
          className="btn-ghost mt-6 border border-stone-200 px-5 py-2 text-sm"
        >
          Try building it now
        </button>
        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
      </div>
    );
  }

  if (!digest && !generating) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="prism-mark mb-4 text-5xl">◭</div>
        <h2 className="font-serif text-2xl font-bold text-stone-900">
          No digest yet
        </h2>
        <p className="mt-2 max-w-sm text-sm text-stone-500">
          Generate your first personalized digest. We’ll rank everything from your
          sources by personal relevance.
        </p>
        <button
          onClick={generate}
          disabled={generating}
          className="btn-primary mt-6 px-6 py-2.5"
        >
          Generate digest
        </button>
        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
      </div>
    );
  }

  if (generating) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="relative mb-6 h-12 w-12">
          <div className="absolute inset-0 animate-spin rounded-full border-2 border-stone-200 border-t-prism-600" />
        </div>
        <h2 className="font-serif text-xl font-semibold text-stone-900">
          Building your digest…
        </h2>
        <p className="mt-2 max-w-sm text-sm text-stone-500">
          Ranking items by personal relevance, deduplicating, and sectioning. This
          takes a few seconds.
        </p>
      </div>
    );
  }

  if (digest) return <DigestView digest={digest} userCreatedAt={userCreatedAt} />;
  return null;
}
