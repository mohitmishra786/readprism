"use client";
/**
 * Client-side service worker registration.
 *
 * Kept separate from the root layout so the layout can stay a server component
 * (Next.js forbids exporting `metadata` from a "use client" module). The SW is
 * intentionally minimal (see public/sw.js) — offline app shell only.
 */
import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // SW registration failures are non-fatal.
      });
    }
  }, []);
  return null;
}
