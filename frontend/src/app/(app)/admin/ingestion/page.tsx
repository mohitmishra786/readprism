"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Report = {
  sources: number;
  fetch_success_rate: number;
  extraction_success_rate: number;
  extraction_by_method: Record<string, number>;
  ingest_to_scored_p50_seconds: number | null;
  storage?: { items: number; full_text_chars: number };
};

export default function IngestionAdminPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/v1/metrics/ingestion`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Report>;
      })
      .then((body) => {
        if (!cancelled) setReport(body);
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
      <h1 className="font-serif text-2xl text-stone-900 dark:text-stone-100">Ingestion</h1>
      <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">
        Fetch success, extraction method, and how long items wait to be scored.
      </p>
      {error && <p className="mt-4 text-sm text-stone-500">Metrics unavailable ({error}).</p>}
      {report && (
        <dl className="mt-6 grid gap-3 text-sm">
          <div>
            <dt className="text-stone-500">Sources</dt>
            <dd className="font-mono text-stone-900 dark:text-stone-100">{report.sources}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Fetch success</dt>
            <dd className="font-mono text-stone-900 dark:text-stone-100">
              {(report.fetch_success_rate * 100).toFixed(1)}%
            </dd>
          </div>
          <div>
            <dt className="text-stone-500">Extraction success</dt>
            <dd className="font-mono text-stone-900 dark:text-stone-100">
              {(report.extraction_success_rate * 100).toFixed(1)}%
            </dd>
          </div>
          <div>
            <dt className="text-stone-500">Methods</dt>
            <dd className="font-mono text-stone-900 dark:text-stone-100">
              {Object.entries(report.extraction_by_method)
                .map(([method, count]) => `${method}: ${count}`)
                .join(", ") || "none"}
            </dd>
          </div>
          <div>
            <dt className="text-stone-500">Ingest to scored, median seconds</dt>
            <dd className="font-mono text-stone-900 dark:text-stone-100">
              {report.ingest_to_scored_p50_seconds ?? "n/a"}
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}
