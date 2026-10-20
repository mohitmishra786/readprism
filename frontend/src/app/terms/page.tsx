import Link from "next/link";

export const metadata = {
  title: "Terms of Service",
  description: "Weirling Terms of Service",
};

// Plain-language terms of service (#178).
// The formal source is docs/TERMS.md.
export default function TermsPage() {
  return (
    <main id="main-content" className="mx-auto max-w-3xl px-5 py-12 text-stone-800 dark:text-stone-100">
      <h1 className="font-serif text-3xl font-bold">Weirling Terms of Service</h1>
      <p className="mt-2 text-xs italic text-stone-500 dark:text-stone-400">
        Last updated: 2026-07-21. Template: not legal advice. Have counsel review and adapt before offering a hosted service.
      </p>
      <p className="mt-4 text-stone-600 dark:text-stone-300">
        These terms govern use of a Weirling instance (&ldquo;the Service&rdquo;). By creating an account you agree to them.
      </p>

      <section className="mt-8" aria-labelledby="the-service">
        <h2 id="the-service" className="text-xl font-semibold">The Service</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          Weirling aggregates content from sources and creators you choose and ranks it by personal relevance.
          Ranking quality depends on behavioural signal that accumulates over time; early digests are necessarily less personalized.
        </p>
      </section>

      <section className="mt-8" aria-labelledby="accounts">
        <h2 id="accounts" className="text-xl font-semibold">Accounts</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          You are responsible for the security of your account and for the activity under it. Provide a valid email address.
          You must be old enough to consent to data processing in your jurisdiction (generally 16 in the EU, 13 in the US).
        </p>
      </section>

      <section className="mt-8" aria-labelledby="acceptable-use">
        <h2 id="acceptable-use" className="text-xl font-semibold">Acceptable use</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">You agree not to:</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-stone-600 dark:text-stone-300">
          <li>add sources or URLs pointing at systems you are not authorized to access, or attempt to make the Service fetch internal/private network resources;</li>
          <li>forward, ingest, or upload content you do not have the right to submit (see <em>Forwarded content</em> below);</li>
          <li>abuse ingestion or digest generation to overload the Service, or attempt to circumvent rate limits, authentication, or per-user data isolation;</li>
          <li>use the Service to infringe intellectual-property or privacy rights.</li>
        </ul>
      </section>

      <section className="mt-8" aria-labelledby="forwarded-content">
        <h2 id="forwarded-content" className="text-xl font-semibold">Forwarded content (newsletters)</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          When you forward a newsletter to your Weirling inbox address, <strong>you confirm you are permitted to forward that content</strong> and to have it processed on the Service. Forwarded newsletters are treated as private to your account and are not shown to other users. We may block or discard forwarded content that appears abusive.
        </p>
      </section>

      <section className="mt-8" aria-labelledby="third-party-content">
        <h2 id="third-party-content" className="text-xl font-semibold">Third-party content</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          The Service fetches and summarizes third-party content and links back to the original source. Summaries are machine-generated and may be inaccurate; the original publisher owns their content. We honour robots.txt and identify our fetcher honestly by default. If you are a content owner and want your content excluded, contact the operator.
        </p>
      </section>

      <section className="mt-8" aria-labelledby="scraping">
        <h2 id="scraping" className="text-xl font-semibold">Scraping and automated access</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          The Service performs automated fetching of public web content. Operators are responsible for using it in compliance with applicable law and the terms of the sites they fetch. The default posture identifies the fetcher as a bot and backs off when blocked.
        </p>
      </section>

      <section className="mt-8" aria-labelledby="paid-tiers">
        <h2 id="paid-tiers" className="text-xl font-semibold">Paid tiers</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          Where a paid tier is offered, its features, price, and billing terms are shown at the point of purchase. (Billing is not enabled in the open-source distribution.)
        </p>
      </section>

      <section className="mt-8" aria-labelledby="liability">
        <h2 id="liability" className="text-xl font-semibold">Disclaimers and liability</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          The Service is provided &ldquo;as is,&rdquo; without warranties. To the extent permitted by law, the operator is not liable for indirect or consequential damages, or for the accuracy of third-party content or machine-generated summaries.
        </p>
      </section>

      <section className="mt-8" aria-labelledby="termination">
        <h2 id="termination" className="text-xl font-semibold">Termination</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          You may delete your account at any time (<code>DELETE /api/v1/account</code> or via Preferences &rarr; Your Data), which erases your data. The operator may suspend accounts that violate these terms.
        </p>
      </section>

      <section className="mt-8" aria-labelledby="changes">
        <h2 id="changes" className="text-xl font-semibold">Changes</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          We may update these terms; material changes will be posted here with a new date. Continued use after changes constitutes acceptance.
        </p>
      </section>

      <div className="mt-12 border-t border-stone-200 pt-6 text-sm text-stone-500 dark:border-stone-800">
        <p>
          See also: <Link href="/privacy" className="underline hover:text-stone-700 dark:hover:text-stone-300">Privacy policy</Link>
        </p>
      </div>
    </main>
  );
}
