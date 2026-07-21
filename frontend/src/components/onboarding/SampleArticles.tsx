"use client";

// A curated, deliberately diverse set spanning distinct topic clusters. Titles
// are embedded server-side, so spreading them across the embedding space (ML,
// systems, web, science, finance, health, design, climate, humanities) makes
// the ratings yield well-separated interest nodes rather than one blurry
// centroid (audit 10-2; pairs with the per-cluster ranking in 05-2).
const SAMPLES = [
  { url: "https://example.com/llm", title: "How large language models actually learn from text", domain: "AI / ML" },
  { url: "https://example.com/rust", title: "Rust vs Go for systems programming in 2026", domain: "Systems programming" },
  { url: "https://example.com/webperf", title: "Making the web fast: Core Web Vitals in practice", domain: "Web development" },
  { url: "https://example.com/crispr", title: "CRISPR base editing reaches the clinic", domain: "Science / biology" },
  { url: "https://example.com/rates", title: "How interest rates ripple through startup funding", domain: "Finance / economics" },
  { url: "https://example.com/sleep", title: "What the latest sleep research says about focus", domain: "Health" },
  { url: "https://example.com/typography", title: "The quiet craft of editorial typography", domain: "Design" },
  { url: "https://example.com/grid", title: "Why the power grid is the hardest climate problem", domain: "Climate / energy" },
  { url: "https://example.com/rome", title: "What the fall of Rome teaches about institutions", domain: "History" },
];

export interface SampleRating {
  article_url: string;
  title: string;
  rating: number;
}

interface SampleArticlesProps {
  ratings: SampleRating[];
  onRate: (ratings: SampleRating[]) => void;
}

export function SampleArticles({ ratings, onRate }: SampleArticlesProps) {
  const getRating = (url: string) =>
    ratings.find((r) => r.article_url === url)?.rating ?? null;

  const rate = (url: string, title: string, rating: number) => {
    const next = ratings.filter((r) => r.article_url !== url);
    onRate([...next, { article_url: url, title, rating }]);
  };

  return (
    <div>
      <p style={{ color: "#6b7280", marginBottom: 16 }}>
        Rate these sample articles to help calibrate your feed.
      </p>
      {SAMPLES.map((s) => {
        const r = getRating(s.url);
        return (
          <div
            key={s.url}
            style={{
              padding: 16,
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              marginBottom: 10,
              background: "#fff",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span
                  style={{
                    fontSize: 11,
                    background: "#f3f4f6",
                    color: "#6b7280",
                    padding: "2px 6px",
                    borderRadius: 10,
                    marginRight: 8,
                  }}
                >
                  {s.domain}
                </span>
                <span style={{ fontWeight: 500 }}>{s.title}</span>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                {[{ v: 1, l: "Would read" }, { v: 0, l: "Maybe" }, { v: -1, l: "Not for me" }].map(
                  ({ v, l }) => (
                    <button
                      key={v}
                      onClick={() => rate(s.url, s.title, v)}
                      style={{
                        padding: "4px 10px",
                        fontSize: 12,
                        border: "1px solid",
                        borderColor: r === v ? "#2563eb" : "#d1d5db",
                        background: r === v ? "#eff6ff" : "#fff",
                        color: r === v ? "#1d4ed8" : "#374151",
                        borderRadius: 6,
                        cursor: "pointer",
                      }}
                    >
                      {l}
                    </button>
                  )
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
