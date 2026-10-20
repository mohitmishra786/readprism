import Link from "next/link";
import { SUBPROCESSORS } from "../../lib/subprocessors";

export const metadata = {
  title: "Subprocessors & Third-Party Services",
  description: "Third-party services, data received, and processing locations for ReadPrism.",
};

// Plain-language subprocessors list (#182).
// The formal source is docs/THIRD_PARTY_SERVICES.md.
export default function SubprocessorsPage() {
  return (
    <main id="main-content" className="mx-auto max-w-4xl px-5 py-12 text-stone-800 dark:text-stone-100">
      <h1 className="font-serif text-3xl font-bold">Third-Party Services &amp; Subprocessors</h1>
      <p className="mt-2 text-xs italic text-stone-500 dark:text-stone-400">
        Template: not legal advice. Have counsel review and adapt before offering a hosted service.
      </p>
      <p className="mt-4 text-stone-600 dark:text-stone-300">
        ReadPrism integrates the third-party services listed below to deliver content aggregation,
        AI-assisted summarization, newsletter processing, and subscription management. This page records
        what data each service receives, where processing occurs, and relevant terms.
      </p>

      <section className="mt-8" aria-labelledby="subprocessors-table">
        <h2 id="subprocessors-table" className="text-xl font-semibold">Active Subprocessors</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <caption className="sr-only">List of subprocessors and third-party services</caption>
            <thead>
              <tr className="border-b border-stone-200 dark:border-stone-700 font-semibold">
                <th scope="col" className="py-2 pr-3">Service</th>
                <th scope="col" className="py-2 pr-3">Purpose / Used for</th>
                <th scope="col" className="py-2 pr-3">Data sent</th>
                <th scope="col" className="py-2 pr-3">Location</th>
                <th scope="col" className="py-2">Notes</th>
              </tr>
            </thead>
            <tbody>
              {SUBPROCESSORS.map((s) => (
                <tr
                  key={s.service}
                  data-testid="subprocessor-row"
                  className="border-b border-stone-100 align-top dark:border-stone-800"
                >
                  <td className="py-2.5 pr-3 font-medium text-stone-900 dark:text-stone-100">
                    {s.service}
                  </td>
                  <td className="py-2.5 pr-3 text-stone-600 dark:text-stone-300">
                    {s.usedFor}
                  </td>
                  <td className="py-2.5 pr-3 text-stone-600 dark:text-stone-300">
                    {s.dataSent}
                  </td>
                  <td className="py-2.5 pr-3 text-stone-600 dark:text-stone-300">
                    {s.location}
                  </td>
                  <td className="py-2.5 text-xs text-stone-500 dark:text-stone-400">
                    {s.termsNotes}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-10" aria-labelledby="dpa-info">
        <h2 id="dpa-info" className="text-xl font-semibold">Data Processing Addendum (DPA)</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          For business customers subject to GDPR or equivalent privacy regulations, a standard Data
          Processing Addendum based on our template (<code>docs/DPA_TEMPLATE.md</code>) is available upon request.
        </p>
      </section>

      <div className="mt-12 border-t border-stone-200 pt-6 text-sm text-stone-500 dark:border-stone-800">
        <p>
          See also:{" "}
          <Link href="/privacy" className="underline hover:text-stone-700 dark:hover:text-stone-300">
            Privacy policy
          </Link>{" "}
          &middot;{" "}
          <Link href="/terms" className="underline hover:text-stone-700 dark:hover:text-stone-300">
            Terms of Service
          </Link>
        </p>
      </div>
    </main>
  );
}
