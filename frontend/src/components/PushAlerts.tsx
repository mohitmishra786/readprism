"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

/** VAPID key (base64url) -> the byte array PushManager.subscribe wants. */
export function keyBytes(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

type State = "loading" | "unsupported" | "off-server" | "denied" | "off" | "on";

// Digest alerts on this device (#266). Opt-in per device: nothing is sent to
// a device until its owner turns this on here.
export function PushAlerts() {
  const [state, setState] = useState<State>("loading");
  const [key, setKey] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    (async () => {
      if (typeof window === "undefined" || !("serviceWorker" in navigator) || !("PushManager" in window)) {
        setState("unsupported");
        return;
      }
      try {
        setKey((await api.push.publicKey()).public_key);
      } catch {
        setState("off-server");
        return;
      }
      if (Notification.permission === "denied") {
        setState("denied");
        return;
      }
      const reg = await navigator.serviceWorker.ready;
      setState((await reg.pushManager.getSubscription()) ? "on" : "off");
    })().catch(() => setState("unsupported"));
  }, []);

  const turnOn = async () => {
    setNote("");
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      setState(permission === "denied" ? "denied" : "off");
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(key) as BufferSource,
    });
    await api.push.subscribe(sub.toJSON());
    setState("on");
  };

  const turnOff = async () => {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await api.push.unsubscribe(sub.endpoint).catch(() => {});
      await sub.unsubscribe();
    }
    setState("off");
  };

  const test = async () => {
    const r = await api.push.test().catch(() => null);
    setNote(r && r.sent > 0 ? "Sent. It should appear in a few seconds." : "Couldn't deliver a test alert.");
  };

  if (state === "loading") return null;
  return (
    <div className="text-sm">
      {state === "unsupported" && (
        <p className="text-stone-500 dark:text-stone-400">
          This browser doesn&apos;t support push alerts. On iPhone, add ReadPrism to your home screen first.
        </p>
      )}
      {state === "off-server" && (
        <p className="text-stone-500 dark:text-stone-400">Push alerts aren&apos;t set up on this instance.</p>
      )}
      {state === "denied" && (
        <p className="text-stone-500 dark:text-stone-400">
          Notifications are blocked for this site; allow them in your browser settings to turn alerts on.
        </p>
      )}
      {(state === "off" || state === "on") && (
        <div className="flex flex-wrap items-center gap-3">
          <span>{state === "on" ? "On for this device." : "Get a notification on this device when your digest is ready."}</span>
          {state === "off" ? (
            <button type="button" onClick={turnOn} className="rounded border border-stone-300 px-3 py-1 dark:border-stone-600">
              Turn on
            </button>
          ) : (
            <>
              <button type="button" onClick={test} className="rounded border border-stone-300 px-3 py-1 dark:border-stone-600">
                Send a test
              </button>
              <button type="button" onClick={turnOff} className="rounded border border-stone-300 px-3 py-1 dark:border-stone-600">
                Turn off
              </button>
            </>
          )}
        </div>
      )}
      {note && <p className="mt-2 text-stone-500 dark:text-stone-400">{note}</p>}
    </div>
  );
}
