"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

// Shown while the instance requires email confirmation and it is pending
// (#175): digests are readable here but not emailed until then.
export function VerifyEmailBanner() {
  const [email, setEmail] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  useEffect(() => {
    api.auth
      .me()
      .then((user) => {
        if (user.email_verified === false) setEmail(user.email);
      })
      .catch(() => {});
  }, []);

  if (!email) return null;

  return (
    <div
      role="status"
      className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
    >
      Confirm <strong>{email}</strong> to get your digest by email.{" "}
      {status === "sent" ? (
        <span>Sent. Check your inbox.</span>
      ) : (
        <button
          type="button"
          disabled={status === "sending"}
          onClick={() => {
            setStatus("sending");
            api.auth
              .resendVerification()
              .then(() => setStatus("sent"))
              .catch(() => setStatus("error"));
          }}
          className="font-medium underline disabled:opacity-50"
        >
          {status === "error" ? "Couldn't send, try again" : "Resend the link"}
        </button>
      )}
    </div>
  );
}
