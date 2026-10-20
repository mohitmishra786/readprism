"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

const HEALTH =
  "border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200";
// Re-checked while the app is open, so a stopped worker shows within the hour.
const HEALTH_POLL_MS = 10 * 60 * 1000;

type Problem = { key: string; message: string; hint: string };

const NOTICE =
  "border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200";

// Account-level notices under the header:
// - email confirmation pending (#175): digests are readable here but not
//   emailed until then;
// - hosted fetch budget used up (#169): feed fetching resumes at a time;
// - instance health, for the owner only (#234): a stopped worker or
//   scheduler, stalled feeds, a backed-up queue or a failing LLM key.
export function AccountNotices() {
  const [problems, setProblems] = useState<Problem[]>([]);
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

  useEffect(() => {
    const load = () =>
      api.metrics
        .instanceHealth()
        .then((r) => setProblems(r.problems))
        .catch(() => {});
    load();
    const timer = window.setInterval(load, HEALTH_POLL_MS);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <>
      {problems.length > 0 && (
        <div role="alert" className={HEALTH}>
          <p className="font-medium">This ReadPrism instance needs attention:</p>
          <ul className="mt-1 list-disc pl-5">
            {problems.map((p) => (
              <li key={p.key}>
                {p.message} <span className="opacity-80">{p.hint}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
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
