"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

const POLL_MS = 3000;
const GIVE_UP_MS = 90_000;

export function elapsedSeconds(sentAt: string, receivedAt: string): number {
  return Math.max(0, Math.round((Date.parse(receivedAt) - Date.parse(sentAt)) / 1000));
}

// The user's personal newsletter address (#151): copy it, set up forwarding,
// and send a test that confirms mail reaches ReadPrism end to end.
export function NewsletterAddressCard() {
  const [info, setInfo] = useState<{ address: string; inbound_configured: boolean; email_verified: boolean } | null>(null);
  const [copied, setCopied] = useState(false);
  const [test, setTest] = useState<"idle" | "sending" | "waiting" | "received" | "timeout" | "error">("idle");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    api.newsletter.address().then(setInfo).catch(() => {});
  }, []);

  if (!info) return null;

  const copy = async () => {
    await navigator.clipboard?.writeText(info.address).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const sendTest = async () => {
    setTest("sending");
    setDetail("");
    try {
      await api.newsletter.sendTest();
    } catch (e) {
      setTest("error");
      setDetail(e instanceof Error ? e.message : "Couldn't send the test.");
      return;
    }
    setTest("waiting");
    const started = Date.now();
    while (Date.now() - started < GIVE_UP_MS) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      const s = await api.newsletter.testStatus().catch(() => null);
      if (s?.status === "received" && s.sent_at && s.received_at) {
        setTest("received");
        setDetail(`Arrived in ${elapsedSeconds(s.sent_at, s.received_at)} s.`);
        return;
      }
    }
    setTest("timeout");
  };

  return (
    <div className="rounded-lg border border-stone-200 p-4 text-sm">
      <p className="font-medium">Your newsletter address</p>
      <div className="mt-2 flex items-center gap-2">
        <code className="flex-1 truncate rounded bg-stone-100 px-2 py-1 dark:bg-stone-800">{info.address}</code>
        <button type="button" onClick={copy} className="rounded border border-stone-300 px-2 py-1">
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <p className="mt-2 text-stone-500">
        Subscribe new newsletters with this address, or forward the ones you already get.
      </p>
      <details className="mt-2 text-stone-500">
        <summary>Forward automatically from Gmail or Outlook</summary>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          <li>
            Gmail: Settings → Forwarding and POP/IMAP → Add a forwarding address, then create a
            filter (e.g. from:substack.com) with &ldquo;Forward it to&rdquo; this address.
          </li>
          <li>
            Outlook: Settings → Mail → Rules → Add new rule, condition &ldquo;From&rdquo; the
            newsletter senders, action &ldquo;Forward to&rdquo; this address.
          </li>
        </ul>
      </details>
      {!info.email_verified && (
        <p className="mt-2 text-amber-700">Confirm your email first: newsletters are held until you do.</p>
      )}
      {info.inbound_configured ? (
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            disabled={test === "sending" || test === "waiting"}
            onClick={sendTest}
            className="rounded border border-stone-300 px-3 py-1 disabled:opacity-50"
          >
            Send a test
          </button>
          <span role="status" className="text-stone-500">
            {test === "sending" && "Sending…"}
            {test === "waiting" && "Waiting for it to arrive…"}
            {test === "received" && `Received. Your address works. ${detail}`}
            {test === "timeout" && "Not received yet. Check the instance's inbound mail setup."}
            {test === "error" && detail}
          </span>
        </div>
      ) : (
        <p className="mt-3 text-stone-500">
          Inbound newsletters aren&apos;t set up on this instance yet (NEWSLETTER_DOMAIN and an
          inbound provider; see the deployment docs).
        </p>
      )}
    </div>
  );
}
