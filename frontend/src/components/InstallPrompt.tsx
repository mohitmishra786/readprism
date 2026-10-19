"use client";
/**
 * PWA install prompt (EC-01): captures beforeinstallprompt and shows a small
 * dismissible banner. No Web Push (optional per spec) — see PROGRESS.
 */
import { useState } from "react";
import { useInstallPrompt } from "../lib/useInstallPrompt";

export function InstallPrompt() {
  const { available, install } = useInstallPrompt();
  const [hidden, setHidden] = useState(
    () => typeof window !== "undefined" && window.localStorage.getItem("install-prompt-dismissed") === "1",
  );

  if (!available || hidden) return null;

  const dismiss = () => {
    window.localStorage.setItem("install-prompt-dismissed", "1");
    setHidden(true);
  };

  return (
    <div
      className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl border border-prism-200 bg-white px-4 py-3 shadow-lg dark:bg-stone-900"
      role="complementary"
      aria-label="Install ReadPrism"
    >
      <span className="text-sm text-stone-700 dark:text-stone-200">
        Install ReadPrism for offline reading
      </span>
      <button
        className="btn-primary px-3 py-1.5 text-xs"
        onClick={() => void install()}
      >
        Install
      </button>
      <button
        onClick={dismiss}
        aria-label="Dismiss install prompt"
        className="text-stone-400 hover:text-stone-700"
      >
        ✕
      </button>
    </div>
  );
}
