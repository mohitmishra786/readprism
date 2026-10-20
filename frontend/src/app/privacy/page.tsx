import Link from "next/link";
import { COLLECTED } from "../../lib/collectedData";
import { BROWSER_STORAGE } from "../../lib/cookies";

export const metadata = {
  title: "What we collect and why",
  description: "Every field ReadPrism records about your reading, why, and for how long.",
};

// Plain-language data page (#134): every recorded field, linked from
// onboarding and Preferences. The formal policy is docs/PRIVACY.md.
export default function PrivacyPage() {
  return (
    <main id="main-content" className="mx-auto max-w-3xl px-5 py-12 text-stone-800 dark:text-stone-100">
      <h1 className="font-serif text-3xl font-bold">What ReadPrism collects, and why</h1>
      <p className="mt-3 text-stone-600 dark:text-stone-300">
        ReadPrism ranks articles by how you actually read. That means it records what you open, how far
        you read, and what you rate. Here is every field, in plain language. Nothing is sold, shared with
        advertisers, or sent to analytics companies.
      </p>

      <section className="mt-8" aria-labelledby="controls">
        <h2 id="controls" className="text-xl font-semibold">Your controls</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          <li><strong>See and edit what was learned:</strong> the <Link className="underline" href="/interests">interest map</Link>.</li>
          <li><strong>Download everything:</strong> Preferences → Your Data → Export (a portable JSON file).</li>
          <li><strong>Delete everything:</strong> Preferences → Your Data → Delete account. It is permanent and immediate.</li>
          <li><strong>Leave the crowd counts:</strong> Preferences → Your Data, untick &ldquo;Count my reading…&rdquo;.</li>
          <li><strong>Email:</strong> turn digest, weekly and alert emails on or off in Preferences, or use the link in any email.</li>
        </ul>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
          On a self-hosted instance, the person who runs it holds this data, on their own server.
        </p>
      </section>

      {COLLECTED.map((t) => (
        <section key={t.table} className="mt-10" aria-labelledby={`t-${t.table}`}>
          <h2 id={`t-${t.table}`} className="text-xl font-semibold">{t.title}</h2>
          <p className="mt-1 text-sm text-stone-600 dark:text-stone-300">{t.summary}</p>
          <p className="mt-1 text-sm"><strong>How long:</strong> {t.retention}</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t.title}: fields</caption>
              <thead>
                <tr className="border-b border-stone-200 dark:border-stone-700">
                  <th scope="col" className="py-1 pr-3">Field</th>
                  <th scope="col" className="py-1 pr-3">What it is</th>
                  <th scope="col" className="py-1">Why</th>
                </tr>
              </thead>
              <tbody>
                {t.fields.map((f) => (
                  <tr key={f.field} className="border-b border-stone-100 align-top dark:border-stone-800">
                    <td className="py-1 pr-3 font-mono text-xs">{f.field}</td>
                    <td className="py-1 pr-3">{f.what}</td>
                    <td className="py-1">{f.why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <section className="mt-10" aria-labelledby="other">
        <h2 id="other" className="text-xl font-semibold">Everything else</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          <li><strong>Account:</strong> your email, a one-way hash of your password, your name and your settings.</li>
          <li><strong>What you follow:</strong> your sources, creators, and the newsletters sent to your ReadPrism address (visible only to you).</li>
          <li><strong>What was learned:</strong> your interest map (topics and weights) and how much you trust each source.</li>
          <li><strong>Articles:</strong> the full text of an article is shortened to an excerpt after 90 days.</li>
        </ul>
      </section>
      <section className="mt-10" aria-labelledby="cookies">
        <h2 id="cookies" className="text-xl font-semibold">Cookies and browser storage</h2>
        <p className="mt-1 text-sm text-stone-600 dark:text-stone-300">
          ReadPrism uses only what it needs to sign you in, keep your account safe and remember your
          settings. There are no analytics, advertising or tracking cookies, and nothing from other
          companies, so there is nothing to consent to and no banner.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Cookies and browser storage</caption>
            <thead>
              <tr className="border-b border-stone-200 dark:border-stone-700">
                <th scope="col" className="py-1 pr-3">Name</th>
                <th scope="col" className="py-1 pr-3">Type</th>
                <th scope="col" className="py-1 pr-3">Why</th>
                <th scope="col" className="py-1">How long</th>
              </tr>
            </thead>
            <tbody>
              {BROWSER_STORAGE.map((c) => (
                <tr key={c.name} className="border-b border-stone-100 align-top dark:border-stone-800">
                  <td className="py-1 pr-3 font-mono text-xs">{c.name}</td>
                  <td className="py-1 pr-3">{c.kind}</td>
                  <td className="py-1 pr-3">{c.purpose}</td>
                  <td className="py-1">{c.lifetime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
