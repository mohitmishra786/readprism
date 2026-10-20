"use client";

import { useEffect, useState } from "react";
import { api } from "../../../../lib/api";
import type { ProductDashboard } from "../../../../lib/types";

// North Star and input metrics (#131). Owner only; computed from this
// instance's own rows, nothing leaves the server.

const pct = (v: number | null) => (v === null ? "No data yet" : `${Math.round(v * 100)}%`);
const num = (v: number | null, unit = "") => (v === null ? "No data yet" : `${v}${unit}`);

type Key = keyof ProductDashboard["now"];

const CARDS: { key: Key; label: string; explain: string; show: (v: number | null) => string }[] = [
  {
    key: "weekly_satisfied_readers",
    label: "Weekly satisfied readers",
    explain: "Opened 3+ digests and finished 3+ items in the last 7 days. The North Star.",
    show: (v) => num(v),
  },
  {
    key: "ttfgd_minutes_median",
    label: "Time to first good digest",
    explain: "Sign-up to a digest with 5+ items across 3+ topics (median, last 30 days' sign-ups).",
    show: (v) => num(v, " min"),
  },
  {
    key: "interleaving_win_rate",
    label: "Ranking win rate",
    explain: "Personal ranking vs newest-first, decided digests in the last 7 days.",
    show: pct,
  },
  {
    key: "retention_d7",
    label: "D7 retention",
    explain: "Opened a digest in days 7 to 13 after signing up (sign-ups 7 to 37 days ago).",
    show: pct,
  },
  {
    key: "retention_d30",
    label: "D30 retention",
    explain: "Opened a digest in days 30 to 36 after signing up (sign-ups 30 to 60 days ago).",
    show: pct,
  },
  {
    key: "top5_wanted_median",
    label: "Top-5 wanted",
    explain: "Median answer to \"how many of today's top 5 did you want?\" (last 30 days).",
    show: (v) => num(v, " of 5"),
  },
  {
    key: "feed_health",
    label: "Feed health",
    explain: "Share of followed feeds that are healthy right now.",
    show: pct,
  },
];

export default function ProductMetricsPage() {
  const [data, setData] = useState<ProductDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.metrics
      .product()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Unavailable"));
  }, []);

  return (
    <section>
      <h1 className="font-serif text-2xl text-stone-900 dark:text-stone-100">Product metrics</h1>
      <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
        From this instance&apos;s own records; nothing leaves the server. Only you, the owner, can
        see this.
      </p>
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}
      {data && !data.enabled && (
        <p className="mt-6 text-sm text-stone-600 dark:text-stone-300" role="status">
          Event recording is off on this instance (PRODUCT_METRICS). Feed health and the ranking
          win rate still work; the rest needs events.
        </p>
      )}
      {data && (
        <>
          <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CARDS.map((c) => (
              <div key={c.key} className="card p-4" data-testid={`metric-${c.key}`}>
                <dt className="text-xs text-stone-500 dark:text-stone-400">{c.label}</dt>
                <dd className="mt-1 text-xl font-semibold">{c.show(data.now[c.key])}</dd>
                <dd className="mt-1 text-xs text-stone-500 dark:text-stone-400">{c.explain}</dd>
                {data.targets[c.key] && (
                  <dd className="mt-1 text-xs text-stone-500 dark:text-stone-400">
                    Target {data.targets[c.key]}
                  </dd>
                )}
              </div>
            ))}
          </dl>
          <h2 className="mt-10 text-lg font-semibold">Events, last 30 days</h2>
          <table className="mt-3 text-sm">
            <tbody>
              {Object.entries(data.events_last_30_days).map(([event, n]) => (
                <tr key={event}>
                  <td className="py-1 pr-6 text-stone-600 dark:text-stone-300">
                    {event.replaceAll("_", " ")}
                  </td>
                  <td className="py-1 tabular-nums">{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
