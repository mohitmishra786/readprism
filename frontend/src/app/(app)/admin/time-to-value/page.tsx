"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Ttv = {
  users_measured: number;
  median_hours_signup_to_first_digest: number | null;
  median_hours_first_digest_to_first_read: number | null;
};

export default function TimeToValuePage() {
  const [ttv, setTtv] = useState<Ttv | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/v1/metrics/time-to-value`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Ttv>;
      })
      .then((body) => {
        if (!cancelled) setTtv(body);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section>
      <h1 className="font-serif text-2xl text-stone-900 dark:text-stone-100">Time to value</h1>
      <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
        Local-only: computed from this instance&apos;s own rows, nothing leaves the box.
      </p>
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}
      {ttv && (
        <dl className="mt-6 grid gap-4 sm:grid-cols-3">
          <div className="card p-4">
            <dt className="text-xs text-stone-500 dark:text-stone-400">Users measured</dt>
            <dd className="mt-1 text-xl font-semibold">{ttv.users_measured}</dd>
          </div>
          <div className="card p-4">
            <dt className="text-xs text-stone-500 dark:text-stone-400">
              Signup → first digest (median)
            </dt>
            <dd className="mt-1 text-xl font-semibold">
              {ttv.median_hours_signup_to_first_digest === null
                ? "—"
                : `${ttv.median_hours_signup_to_first_digest} h`}
            </dd>
          </div>
          <div className="card p-4">
            <dt className="text-xs text-stone-500 dark:text-stone-400">
              First digest → first read (median)
            </dt>
            <dd className="mt-1 text-xl font-semibold">
              {ttv.median_hours_first_digest_to_first_read === null
                ? "—"
                : `${ttv.median_hours_first_digest_to_first_read} h`}
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}
