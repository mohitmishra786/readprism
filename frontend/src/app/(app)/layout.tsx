"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { getRefreshToken, isAuthenticated, removeToken } from "../../lib/auth";

const NAV = [
  { href: "/digest", label: "Digest" },
  { href: "/feed", label: "Feed" },
  { href: "/sources", label: "Sources" },
  { href: "/creators", label: "Creators" },
  { href: "/search", label: "Search" },
  { href: "/preferences", label: "Preferences" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (!isAuthenticated()) router.replace("/login");
  }, [router]);

  if (!mounted) return null;

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="sticky top-0 z-40 border-b border-stone-200 bg-white/80 backdrop-blur-lg">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-1 px-4">
          <Link
            href="/digest"
            className="prism-mark mr-4 text-lg"
            aria-label="ReadPrism home"
          >
            ◭ ReadPrism
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
                      ? "bg-stone-900 text-white"
                      : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <button
            onClick={() => {
              const refresh = getRefreshToken();
              if (refresh) {
                // Best-effort server-side revocation; don't block sign-out on it.
                api.auth.logout(refresh).catch(() => {});
              }
              removeToken();
              router.replace("/login");
            }}
            className="ml-auto text-sm text-stone-500 transition-colors hover:text-stone-900"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">{children}</main>
    </div>
  );
}
