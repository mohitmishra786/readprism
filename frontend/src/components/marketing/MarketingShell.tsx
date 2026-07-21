import Link from "next/link";

// Static, text-rich shell for the indexable marketing/comparison routes (audit
// 11-3). Server component (no "use client"), so it's SSG + crawlable.
export function MarketingShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <header className="border-b border-stone-200 dark:border-stone-800">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
          <Link href="/" className="font-serif text-lg font-bold">
            ◭ ReadPrism
          </Link>
          <nav className="flex gap-4 text-sm text-stone-600 dark:text-stone-400">
            <Link href="/how-it-works" className="hover:text-prism-700">
              How it works
            </Link>
            <Link href="/register" className="hover:text-prism-700">
              Get started
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-12">{children}</main>
      <footer className="border-t border-stone-200 px-4 py-8 text-center text-sm text-stone-500 dark:border-stone-800">
        <p>
          ReadPrism — behavioral, explainable, open-source content ranking.{" "}
          <a
            href="https://github.com/mohitmishra786/readprism"
            className="underline hover:text-prism-700"
          >
            Source on GitHub
          </a>
        </p>
      </footer>
    </div>
  );
}
