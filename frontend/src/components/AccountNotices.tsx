"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

const NOTICE =
  "border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200";

// Account-level notices under the header:
// - email confirmation pending (#175): digests are readable here but not
//   emailed until then;
// - hosted fetch budget used up (#169): feed fetching resumes at a time.
export function AccountNotices() {
  const [email, setEmail] = useState<string | null>(null);
  const [pausedUntil, setPausedUntil] = useState<Date | null>(null);
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  useEffect(() => {
    api.auth
      .me()
      .then((user) => {
        if (user.email_verified === false) setEmail(user.email);
        const until = user.fetch_paused_until ? new Date(user.fetch_paused_until) : null;
        if (until && until.getTime() > Date.now()) setPausedUntil(until);
      })
      .catch(() => {});
  }, []);

  return (
    <>
      {pausedUntil && (
        <div role="status" className={NOTICE}>
          Feed fetching is paused: this account used its hourly fetch budget. It resumes at{" "}
          {pausedUntil.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.
        </div>
      )}
      {email && <VerifyEmailNotice email={email} status={status} setStatus={setStatus} />}
    </>
  );
}

function VerifyEmailNotice({
  email,
  status,
  setStatus,
}: {
  email: string;
  status: "idle" | "sending" | "sent" | "error";
  setStatus: (s: "idle" | "sending" | "sent" | "error") => void;
}) {
  return (
    <div role="status" className={NOTICE}>
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
