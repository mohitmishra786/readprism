'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getContactInfo } from '../../lib/api';

export default function ContactPage() {
  const [grievanceEmail, setGrievanceEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getContactInfo()
      .then((info) => {
        setGrievanceEmail(info.grievance_contact_email);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  return (
    <main id="main-content" className="mx-auto max-w-3xl px-5 py-12 text-stone-800 dark:text-stone-100">
      <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
        <strong>Template: not legal advice.</strong> Review with counsel for your specific operating jurisdiction.
      </div>

      <h1 className="font-serif text-3xl font-bold">Contact</h1>
      <p className="mt-3 text-stone-600 dark:text-stone-300">
        Get in touch with the ReadPrism project. For general issues, bugs, and feature discussions, visit our{' '}
        <a
          href="https://github.com/mohitmishra786/readprism"
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
        >
          GitHub repository
        </a>{' '}
        or{' '}
        <a
          href="https://github.com/mohitmishra786/readprism/discussions"
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
        >
          GitHub Discussions
        </a>.
      </p>

      {!loading && grievanceEmail && (
        <section className="mt-10 rounded-lg border border-stone-200 p-6 dark:border-stone-800" aria-labelledby="takedown-heading">
          <h2 id="takedown-heading" className="text-xl font-semibold">
            Takedown and grievance requests
          </h2>
          <p className="mt-2 text-sm text-stone-600 dark:text-stone-300">
            ReadPrism respects publisher copyrights and content availability controls. If you are a publisher, author, or copyright holder and wish to request removal of your content, feed, or domain from this instance:
          </p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-stone-600 dark:text-stone-300">
            <li>Identify the specific URL(s) or domain to be excluded.</li>
            <li>Provide reasonable proof of authorization or ownership.</li>
            <li>Send your takedown or grievance notice to our designated contact:</li>
          </ul>
          <div className="mt-4">
            <a
              href={`mailto:${grievanceEmail}`}
              className="inline-flex items-center font-mono text-sm font-medium text-purple-700 underline hover:text-purple-900 dark:text-purple-400 dark:hover:text-purple-300"
            >
              {grievanceEmail}
            </a>
          </div>
          <p className="mt-3 text-xs text-stone-500 dark:text-stone-400">
            Valid takedown notices result in instance-wide blocking: matching items are immediately excluded from reader views, search, feeds, digests, and future crawler ingestion.
          </p>
        </section>
      )}

      <div className="mt-10 border-t border-stone-200 pt-6 dark:border-stone-800 text-sm text-stone-500 dark:text-stone-400">
        <Link href="/" className="underline hover:text-stone-700 dark:hover:text-stone-200">
          ← Back to home
        </Link>
      </div>
    </main>
  );
}
