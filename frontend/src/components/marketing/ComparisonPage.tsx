import { MarketingShell } from "./MarketingShell";

export interface ComparisonRow {
  dimension: string;
  competitor: string;
  weirling: string;
}

export interface ComparisonSource {
  label: string;
  url: string;
}

export interface ComparisonData {
  competitor: string;
  intro: string;
  rows: ComparisonRow[];
  differsBecause: string[];
  fairnote: string;
  /** When the competitor's prices and claims were last checked (#168). */
  checked: string;
  sources: ComparisonSource[];
}

/** Our own plans, in one place so every comparison page agrees (D-18). */
export const WEIRLING_PRICING =
  "Self-hosted: free (MIT). Hosted: Reader $6/mo or $54/yr, Pro $12/mo or $108/yr, 30-day Pro trial";

export function ComparisonPage({ data }: { data: ComparisonData }) {
  return (
    <MarketingShell>
      <article className="prose-reader">
        <h1 className="font-playfair text-3xl font-bold">
          Weirling vs {data.competitor}
        </h1>
        <p className="mt-4 text-lg text-stone-600 dark:text-stone-300">{data.intro}</p>

        <div className="mt-8 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-stone-300 dark:border-stone-700">
                <th className="py-2 text-left">&nbsp;</th>
                <th className="py-2 text-left">{data.competitor}</th>
                <th className="py-2 text-left">Weirling</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.dimension} className="border-b border-stone-200 dark:border-stone-800">
                  <td className="py-2 pr-4 font-medium">{r.dimension}</td>
                  <td className="py-2 pr-4 text-stone-600 dark:text-stone-400">{r.competitor}</td>
                  <td className="py-2 text-stone-900 dark:text-stone-100">{r.weirling}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2 className="mt-8 font-playfair text-2xl font-semibold">
          Where Weirling differs
        </h2>
        <ul className="mt-3 list-disc space-y-2 pl-6">
          {data.differsBecause.map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>

        <p className="mt-6 text-sm text-stone-500 dark:text-stone-400">{data.fairnote}</p>

        <p className="mt-6 text-sm text-stone-500 dark:text-stone-400" data-testid="checked">
          Prices and features last checked {data.checked}. Sources:
        </p>
        <ul className="mt-1 list-disc pl-6 text-sm text-stone-500 dark:text-stone-400">
          {data.sources.map((src) => (
            <li key={src.url}>
              <a href={src.url} rel="noopener noreferrer" className="underline">
                {src.label}
              </a>
            </li>
          ))}
        </ul>
        <p className="mt-6">
          <a href="/register" className="text-prism-700 underline dark:text-prism-300">
            Try Weirling
          </a>{" "}
          ·{" "}
          <a href="/how-it-works" className="text-prism-700 underline dark:text-prism-300">
            How the ranking works
          </a>
        </p>
      </article>
    </MarketingShell>
  );
}
