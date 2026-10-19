"use client";
import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/**
 * The browser's PWA install offer, if it made one (EC-01, #201). `available`
 * is false on browsers without beforeinstallprompt (iOS Safari) and once the
 * app is installed, so callers only show an install button when it works.
 */
export function useInstallPrompt(): { available: boolean; install: () => Promise<boolean> } {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  return {
    available: deferred !== null,
    install: async () => {
      if (!deferred) return false;
      await deferred.prompt();
      const choice = await deferred.userChoice.catch(() => ({ outcome: "dismissed" as const }));
      setDeferred(null);
      return choice.outcome === "accepted";
    },
  };
}
