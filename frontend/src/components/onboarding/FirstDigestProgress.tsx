"use client";
import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { api, type FirstDigestStatus } from "../../lib/api";

const POLL_MS = 3000;
// The backend builds at its own 3-minute deadline; stop polling a bit later.
const GIVE_UP_MS = 5 * 60 * 1000;

interface Props {
  /** Called once the first digest exists. */
  onReady: () => void;
}

function Step({ done, active, label }: { done: boolean; active: boolean; label: string }) {
  return (
    <li className="flex items-center gap-3 text-left text-sm">
      <span
        aria-hidden
        className={
          done
            ? "flex h-5 w-5 items-center justify-center rounded-full bg-prism-600 text-xs text-white"
            : active
              ? "h-5 w-5 animate-spin rounded-full border-2 border-stone-200 border-t-prism-600"
              : "h-5 w-5 rounded-full border-2 border-stone-200"
        }
      >
        {done ? <Check className="h-3 w-3" aria-hidden="true" /> : ""}
      </span>
      <span className={done ? "text-stone-900" : "text-stone-500"}>{label}</span>
    </li>
  );
}

/**
 * First-run progress (#102): starts the first-digest flow (idempotent), then
 * shows real counts while the user's sources are fetched, read and ranked.
 */
export function FirstDigestProgress({ onReady }: Props) {
  const [status, setStatus] = useState<FirstDigestStatus | null>(null);
  const [stalled, setStalled] = useState(false);
  const started = useRef<number | null>(null);
  // Keep the latest callback without restarting the polling loop each render.
  const onReadyRef = useRef(onReady);

  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);

  useEffect(() => {
    if (started.current === null) {
      started.current = Date.now();
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async (first: boolean) => {
      try {
        const s = first ? await api.onboarding.startFirstDigest() : await api.onboarding.firstDigestStatus();
        if (cancelled) return;
        setStatus(s);
        if (s.digest_id) {
          onReadyRef.current();
          return;
        }
      } catch {
        // Transient errors: keep polling until the give-up window passes.
      }
      if (started.current && Date.now() - started.current > GIVE_UP_MS) {
        setStalled(true);
        return;
      }
      timer = setTimeout(() => tick(false), POLL_MS);
    };

    tick(true);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const fetched = status ? status.sources_fetched : 0;
  const total = status ? status.sources_total : 0;
  const items = status ? status.items : 0;
  const read = status ? status.items_embedded : 0;
  const sourcesDone = total > 0 && fetched >= total;
  const itemsDone = items >= 5;

  return (
    <div className="flex flex-col items-center justify-center py-20 text-center" aria-live="polite">
      <h2 className="font-serif text-2xl font-bold text-stone-900">Building your first digest</h2>
      <p className="mt-2 max-w-md text-sm text-stone-500">
        We’re fetching your sources and reading the newest articles. This usually takes a
        minute or two; the page updates on its own.
      </p>
      <ul className="mt-8 w-full max-w-xs space-y-3">
        <Step
          done={sourcesDone}
          active={!sourcesDone}
          label={total ? `Fetched ${fetched} of ${total} sources` : "Fetching your sources"}
        />
        <Step done={itemsDone} active={sourcesDone && !itemsDone} label={`${items} new articles found`} />
        <Step
          done={itemsDone && read >= Math.min(items, 5)}
          active={itemsDone}
          label={`${read} articles read and summarized`}
        />
        <Step done={Boolean(status?.digest_id)} active={Boolean(status?.ready)} label="Ranking for you" />
      </ul>
      {stalled && (
        <p className="mt-8 max-w-sm text-sm text-stone-600">
          This is taking longer than usual. Your sources may be slow to respond; your digest
          will appear here as soon as it’s built. You can also add more sources meanwhile.
        </p>
      )}
    </div>
  );
}
