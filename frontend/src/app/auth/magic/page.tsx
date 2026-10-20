"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../../lib/api";

// Verifies a magic-link token and signs the user in (audit 10-8).
export default function MagicVerifyPage() {
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      queueMicrotask(() => setError("This sign-in link is missing its token."));
      return;
    }
    api.auth
      .magicLinkVerify(token)
      .then(() => router.replace("/digest"))
      .catch(() => setError("This sign-in link is invalid or has already been used."));
  }, [router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 text-center">
      {error ? (
        <>
          <h1 className="font-playfair text-xl font-semibold">Sign-in link problem</h1>
          <p className="mt-2 max-w-sm text-sm text-stone-500 dark:text-stone-400">{error}</p>
          <a href="/login" className="mt-4 text-sm text-prism-700 underline dark:text-prism-300">
            Back to sign in
          </a>
        </>
      ) : (
        <>
          <div className="relative mb-4 h-10 w-10">
            <div className="absolute inset-0 animate-spin rounded-full border-2 border-stone-200 border-t-prism-600 dark:border-white/10" />
          </div>
          <p className="text-sm text-stone-500 dark:text-stone-400">Signing you in…</p>
        </>
      )}
    </div>
  );
}
