"use client";

const SAMPLES = [
  { url: "https://example.com/1", title: "How Large Language Models Learn", domain: "AI/ML" },
  { url: "https://example.com/2", title: "The Future of Remote Work in Tech", domain: "Work" },
  { url: "https://example.com/3", title: "Urban Housing Policy in 2025", domain: "Policy" },
  { url: "https://example.com/4", title: "Rust vs Go: Systems Programming in 2025", domain: "Programming" },
  { url: "https://example.com/5", title: "How Interest Rates Affect Startup Funding", domain: "Finance" },
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
