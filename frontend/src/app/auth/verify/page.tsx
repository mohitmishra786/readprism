"use client";
import { useEffect, useState } from "react";
import { api } from "../../../lib/api";

// Confirms an email address from the emailed link (#175).
export default function VerifyEmailPage() {
  const [state, setState] = useState<"pending" | "ok" | "error">("pending");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      queueMicrotask(() => setState("error"));
      return;
    }
    api.auth
      .verifyEmail(token)
      .then(() => setState("ok"))
      .catch(() => setState("error"));
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 text-center">
      {state === "pending" && <p className="text-sm text-stone-500">Confirming your email…</p>}
      {state === "ok" && (
        <>
          <h1 className="font-serif text-xl font-semibold">Email confirmed</h1>
          <p className="mt-2 max-w-sm text-sm text-stone-500">
            Your digest will arrive by email from now on.
          </p>
          <a href="/digest" className="mt-4 text-sm text-prism-700 underline">
            Go to your digest
          </a>
        </>
      )}
      {state === "error" && (
        <>
          <h1 className="font-serif text-xl font-semibold">Confirmation link problem</h1>
          <p className="mt-2 max-w-sm text-sm text-stone-500">
            This link is invalid or has expired. Sign in and use &ldquo;Resend the link&rdquo;
            to get a new one.
          </p>
          <a href="/login" className="mt-4 text-sm text-prism-700 underline">
            Sign in
          </a>
        </>
      )}
    </div>
  );
}
