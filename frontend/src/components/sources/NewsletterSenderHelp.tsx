"use client";
import type { Source } from "../../lib/types";

// Inbox relief for one newsletter sender (#249). The links come from the
// sender's own List-Unsubscribe header (https: and mailto: only, checked
// server-side) and open in a new tab; ReadPrism never follows them itself.
export function NewsletterSenderHelp({ source }: { source: Source }) {
  if (source.source_type !== "newsletter" || !source.newsletter_delivery) return null;
  if (source.newsletter_delivery === "direct") {
    return (
      <p className="mt-1.5 text-xs text-stone-500 dark:text-stone-400">
        Arrives straight at your ReadPrism address: nothing in your inbox to clean up.
      </p>
    );
  }
  const options = source.unsubscribe_options;
  return (
    <details className="mt-1.5 text-xs text-stone-600 dark:text-stone-300">
      <summary className="cursor-pointer">Stop it in your inbox, keep it here</summary>
      <ol className="mt-1 list-decimal space-y-1 pl-5">
        <li>
          Subscribe to this newsletter again with your ReadPrism address (in{" "}
          <a href="/preferences" className="underline">Preferences → Newsletters</a>).
        </li>
        <li>
          Then unsubscribe your inbox copy
          {options?.url || options?.mailto ? ":" : " with the link at the bottom of any issue."}
          {options?.url && (
            <>
              {" "}
              <a href={options.url} target="_blank" rel="noopener noreferrer nofollow" className="font-medium underline">
                unsubscribe page
              </a>
            </>
          )}
          {options?.url && options?.mailto && " or "}
          {options?.mailto && (
            <a href={options.mailto} className="font-medium underline">
              email the sender
            </a>
          )}
          .
        </li>
      </ol>
      <p className="mt-1 text-stone-500 dark:text-stone-400">
        Do step 1 first: unsubscribing also stops the copies you forward to ReadPrism.
      </p>
    </details>
  );
}
