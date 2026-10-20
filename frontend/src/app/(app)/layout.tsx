"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, hasSession } from "../../lib/api";
import { AccountNotices } from "../../components/AccountNotices";

const NAV = [
  { href: "/digest", label: "Digest" },
  { href: "/feed", label: "Feed" },
  { href: "/sources", label: "Sources" },
  { href: "/creators", label: "Creators" },
  { href: "/search", label: "Search" },
  { href: "/interests", label: "Interests" },
  { href: "/preferences", label: "Preferences" },
  { href: "/admin/ingestion", label: "Ingestion" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // Session lives in httpOnly cookies (#103): ask the API instead of
    // reading a token in JavaScript.
    let cancelled = false;
    hasSession().then((signedIn) => {
      if (cancelled) return;
      if (signedIn) setMounted(true);
      else router.replace("/login");
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!mounted) return null;

  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-stone-200 bg-white/80 backdrop-blur-lg dark:border-stone-800 dark:bg-stone-900/80">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-1 px-4">
          <Link
            href="/digest"
            className="prism-mark mr-4 text-lg"
            aria-label="Weirling home"
          >
            ◭ Weirling
          </Link>
          <nav className="flex items-center gap-0.5 overflow-x-auto">
            {NAV.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    active
                      ? "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900"
                      : "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <button
            onClick={async () => {
              // Revokes the refresh token and clears the session cookies.
              await api.auth.logout().catch(() => {});
              router.replace("/login");
            }}
            className="ml-auto text-sm text-stone-500 transition-colors hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"
          >
            Sign out
          </button>
        </div>
      </header>
      <AccountNotices />
      <main id="main-content" className="mx-auto max-w-3xl px-4 py-8">
        {children}
      </main>
    </div>
  );
}
