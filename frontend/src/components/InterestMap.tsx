"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { dropTarget, layout, radiusFor, type Point } from "../lib/forceLayout";
import type { InterestGraph, InterestGraphNode } from "../lib/types";

const W = 1000;
const H = 700;
const RECENT_DAYS = 7;

export function isRecent(node: InterestGraphNode, now = Date.now()): boolean {
  return Boolean(node.last_reinforced_at && now - Date.parse(node.last_reinforced_at) < RECENT_DAYS * 86_400_000);
}

export function isMuted(node: InterestGraphNode, now = Date.now()): boolean {
  return Boolean(node.suppressed_until && Date.parse(node.suppressed_until) > now);
}

function download(name: string, type: string, body: string) {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

// The interest map (#179): every topic Weirling inferred, sized by weight,
// linked when read together. Drag a topic onto another to merge them;
// select one to rename, boost, mute or remove it. The list beside the map
// offers the same actions for keyboard and screen-reader users.
export function InterestMap() {
  const [graph, setGraph] = useState<InterestGraph | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [rename, setRename] = useState("");
  const [mergeInto, setMergeInto] = useState("");
  const [note, setNote] = useState("");
  const [drag, setDrag] = useState<{ id: string; at: Point } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [now] = useState(() => Date.now());

  const load = useCallback(() => {
    api.preferences.interestGraph(300).then(setGraph).catch(() => setGraph({ nodes: [], edges: [] }));
  }, []);
  useEffect(load, [load]);

  const radii = useMemo(
    () => new Map((graph?.nodes ?? []).map((n) => [n.label, radiusFor(n.weight)])),
    [graph],
  );
  const positions = useMemo(() => {
    if (!graph) return new Map<string, Point>();
    return layout(
      graph.nodes.map((n) => ({ id: n.label, radius: radiusFor(n.weight) })),
      graph.edges.map((e) => ({ source: e.from_label, target: e.to_label, weight: e.weight })),
      { width: W, height: H },
    );
  }, [graph]);

  const act = async (label: string, run: () => Promise<unknown>, done: string) => {
    try {
      await run();
      setNote(done);
      setSelected(null);
      load();
    } catch (e) {
      setNote(e instanceof Error ? e.message : `Couldn't update ${label}.`);
    }
  };
  const boost = (l: string) => act(l, () => api.feedback.adjustInterests(l, "boost"), `Boosted “${l}”.`);
  const mute = (l: string, days: number) =>
    act(l, () => api.feedback.adjustInterests(l, "suppress", days), `Muted “${l}” for ${days} days.`);
  const remove = (l: string) => act(l, () => api.feedback.adjustInterests(l, "remove"), `Removed “${l}”.`);
  const doRename = (l: string, to: string) =>
    to.trim() && to.trim() !== l
      ? act(l, () => api.feedback.renameInterest(l, to.trim()), `Renamed “${l}” to “${to.trim()}”.`)
      : undefined;
  const doMerge = (from: string, into: string) =>
    from !== into && window.confirm(`Merge “${from}” into “${into}”?`)
      ? act(from, () => api.feedback.mergeInterests(from, into), `Merged “${from}” into “${into}”.`)
      : undefined;

  const toSvg = (e: React.PointerEvent): Point | null => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height || !Number.isFinite(e.clientX) || !Number.isFinite(e.clientY)) return null;
    return { x: ((e.clientX - rect.left) / rect.width) * W, y: ((e.clientY - rect.top) / rect.height) * H };
  };

  if (!graph) return <p className="text-sm text-stone-500">Loading your interests…</p>;
  if (graph.nodes.length === 0)
    return <p className="text-sm text-stone-500">No interests yet. They appear as you read and rate articles.</p>;

  const pos = (label: string) => (drag?.id === label ? drag.at : positions.get(label));
  const current = graph.nodes.find((n) => n.label === selected) ?? null;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
      <div>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="w-full touch-none select-none rounded-lg border border-stone-200 bg-white dark:border-stone-700 dark:bg-stone-900"
          role="img"
          aria-label={`Map of ${graph.nodes.length} interests; the list beside it has the same topics and actions`}
          onPointerMove={(e) => {
            const at = drag && toSvg(e);
            if (drag && at) setDrag({ id: drag.id, at });
          }}
          onPointerUp={(e) => {
            if (!drag) return;
            const at = toSvg(e) ?? drag.at;
            const target = dropTarget(drag.id, at, positions, radii);
            const moved = Math.hypot(drag.at.x - positions.get(drag.id)!.x, drag.at.y - positions.get(drag.id)!.y) > 6;
            setDrag(null);
            if (target) void doMerge(drag.id, target);
            else if (!moved) setSelected(drag.id);
          }}
          onPointerLeave={() => setDrag(null)}
        >
          {graph.edges.map((e) => {
            const a = pos(e.from_label), b = pos(e.to_label);
            if (!a || !b) return null;
            return (
              <line key={`${e.from_label}|${e.to_label}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                className="stroke-stone-300 dark:stroke-stone-600" strokeOpacity={0.3 + Math.min(0.6, e.weight)} strokeWidth={1 + e.weight * 2} />
            );
          })}
          {graph.nodes.map((n) => {
            const p = pos(n.label);
            if (!p) return null;
            const r = radiusFor(n.weight);
            const muted = isMuted(n, now);
            return (
              <g key={n.label} transform={`translate(${p.x},${p.y})`} className="cursor-grab"
                onPointerDown={(e) => {
                  (e.target as Element).setPointerCapture?.(e.pointerId);
                  setDrag({ id: n.label, at: positions.get(n.label)! });
                }}>
                {isRecent(n, now) && <circle r={r + 5} className="fill-none stroke-amber-400" strokeWidth={3} />}
                <circle r={r}
                  className={muted ? "fill-stone-300 dark:fill-stone-700" : n.is_core ? "fill-prism-600" : "fill-prism-400"}
                  stroke={selected === n.label ? "#f59e0b" : "white"} strokeWidth={selected === n.label ? 4 : 1.5} />
                {(r > 14 || selected === n.label) && (
                  <text y={r + 14} textAnchor="middle" className="fill-stone-700 text-[13px] dark:fill-stone-200">{n.label}</text>
                )}
              </g>
            );
          })}
        </svg>
        <p className="mt-2 text-xs text-stone-500 dark:text-stone-400">
          Bigger = stronger interest. <span className="text-amber-600">Ring</span> = reinforced in the last week.
          Grey = muted. Drag one topic onto another to merge them.
        </p>
        <div className="mt-2 flex gap-2 text-xs">
          <button type="button" className="underline" onClick={() => download("weirling-interests.json", "application/json", JSON.stringify(graph, null, 2))}>
            Export JSON
          </button>
          <button type="button" className="underline" onClick={() => svgRef.current && download("weirling-interests.svg", "image/svg+xml", svgRef.current.outerHTML)}>
            Export image (SVG)
          </button>
        </div>
      </div>

      <aside className="text-sm">
        {note && <p role="status" className="mb-3 text-stone-600 dark:text-stone-300">{note}</p>}
        {current && (
          <div className="mb-4 rounded-lg border border-stone-200 p-3 dark:border-stone-700" aria-label={`Edit ${current.label}`} role="group">
            <p className="font-medium">{current.label}</p>
            <p className="text-xs text-stone-500 dark:text-stone-400">
              Weight {Math.round(current.weight * 100)}% · reinforced {current.reinforcement_count ?? 0} times
              {isMuted(current, now) ? " · muted" : ""}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button type="button" className="rounded border px-2 py-0.5" onClick={() => boost(current.label)}>Boost</button>
              <button type="button" className="rounded border px-2 py-0.5" onClick={() => mute(current.label, 7)}>Mute 7 days</button>
              <button type="button" className="rounded border px-2 py-0.5" onClick={() => mute(current.label, 30)}>Mute 30 days</button>
              <button type="button" className="rounded border px-2 py-0.5" onClick={() => remove(current.label)}>Remove</button>
            </div>
            <form className="mt-2 flex gap-1.5" onSubmit={(e) => { e.preventDefault(); void doRename(current.label, rename); }}>
              <label className="sr-only" htmlFor="rename-topic">New name</label>
              <input id="rename-topic" value={rename} onChange={(e) => setRename(e.target.value)} placeholder="Rename to…"
                className="min-w-0 flex-1 rounded border px-2 py-0.5 dark:bg-stone-900" />
              <button type="submit" className="rounded border px-2 py-0.5">Rename</button>
            </form>
            <form className="mt-2 flex gap-1.5" onSubmit={(e) => { e.preventDefault(); if (mergeInto) void doMerge(current.label, mergeInto); }}>
              <label className="sr-only" htmlFor="merge-into">Merge into</label>
              <select id="merge-into" value={mergeInto} onChange={(e) => setMergeInto(e.target.value)} className="min-w-0 flex-1 rounded border px-1 py-0.5 dark:bg-stone-900">
                <option value="">Merge into…</option>
                {graph.nodes.filter((n) => n.label !== current.label).map((n) => (
                  <option key={n.label} value={n.label}>{n.label}</option>
                ))}
              </select>
              <button type="submit" className="rounded border px-2 py-0.5">Merge</button>
            </form>
          </div>
        )}
        <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">All topics</h2>
        <ul className="max-h-[28rem] space-y-0.5 overflow-auto">
          {graph.nodes.map((n) => (
            <li key={n.label}>
              <button type="button" aria-pressed={selected === n.label}
                onClick={() => { setSelected(n.label); setRename(n.label); setMergeInto(""); }}
                className="flex w-full justify-between rounded px-1.5 py-0.5 text-left hover:bg-stone-100 dark:hover:bg-stone-800">
                <span className={isMuted(n, now) ? "text-stone-400 line-through" : ""}>
                  {n.label}{isRecent(n, now) ? " •" : ""}
                </span>
                <span className="tabular-nums text-stone-500">{Math.round(n.weight * 100)}%</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
