import type { Metadata } from "next";
import { MarketingShell } from "../../components/marketing/MarketingShell";

export const metadata: Metadata = {
  title: "Hosted Weirling — early access",
  description:
    "A hosted Weirling (no self-hosting required) is planned for knowledge workers. Register interest and get notified when the beta opens.",
  alternates: { canonical: "/waitlist" },
};

// Captures ICP-#2 (knowledge-worker) demand we can't yet serve (audit 14-2).
export default function Waitlist() {
  return (
    <MarketingShell>
      <article className="prose-reader">
        <h1 className="font-playfair text-3xl font-bold">Hosted Weirling — early access</h1>
        <p className="mt-4 text-lg text-stone-600 dark:text-stone-300">
          Weirling is open source and self-hostable today. A fully-hosted option
          — no Docker, no server — is planned for people who want the behavioral
          ranking without running the stack. Want to know when the beta opens?
        </p>
        <ul className="mt-6 list-disc space-y-2 pl-6">
          <li>
            <strong>Get notified:</strong>{" "}
            <a
              href="mailto:hello@weirling.com?subject=Weirling%20hosted%20beta%20waitlist"
              className="text-prism-700 underline dark:text-prism-300"
            >
              email us to join the waitlist
            </a>
            .
          </li>
          <li>
            <strong>Follow along:</strong>{" "}
            <a
              href="https://github.com/mohitmishra786/weirling"
              className="text-prism-700 underline dark:text-prism-300"
            >
              star / watch the repo
            </a>{" "}
            for build-in-public updates.
          </li>
          <li>
            <strong>Try it now:</strong> self-host in a few minutes —{" "}
            <a href="/how-it-works" className="text-prism-700 underline dark:text-prism-300">
              see how it works
            </a>
            .
          </li>
        </ul>
        <p className="mt-6 text-sm text-stone-500 dark:text-stone-400">
          We&apos;ll only email you about the hosted beta. No spam.
        </p>
      </article>
    </MarketingShell>
  );
}
