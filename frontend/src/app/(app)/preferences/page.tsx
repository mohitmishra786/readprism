"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../../lib/api";
import type { InterestGraph, InterestGraphEdge, InterestGraphNode, User } from "../../../lib/types";

// --- Simple force-layout SVG graph ---
const SVG_W = 600;
const SVG_H = 360;
const NODE_R = 18;

function layoutNodes(nodes: InterestGraphNode[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const count = Math.min(nodes.length, 24);
  for (let i = 0; i < count; i++) {
    const angle = (2 * Math.PI * i) / count;
    const r = SVG_H / 2 - NODE_R - 10;
    positions.set(nodes[i].label, {
      x: SVG_W / 2 + r * Math.cos(angle),
      y: SVG_H / 2 + r * Math.sin(angle),
    });
  }
  return positions;
}

function InterestGraphSVG({
  nodes,
  edges,
}: {
  nodes: InterestGraphNode[];
  edges: InterestGraphEdge[];
}) {
  const visible = nodes.slice(0, 24);
  const labelSet = useMemo(() => new Set(visible.map((n) => n.label)), [visible]);
  const positions = useMemo(() => layoutNodes(visible), [visible]);
  const visibleEdges = edges.filter(
    (e) => labelSet.has(e.from_label) && labelSet.has(e.to_label) && e.weight > 0.1
  );

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${SVG_W} ${SVG_H}`}
      style={{ background: "#f8fafc", borderRadius: 8, border: "1px solid #e5e7eb" }}
    >
      {visibleEdges.map((edge, i) => {
        const from = positions.get(edge.from_label);
        const to = positions.get(edge.to_label);
        if (!from || !to) return null;
        return (
          <line
            key={i}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke="#bfdbfe"
            strokeWidth={Math.max(0.5, edge.weight * 3)}
            opacity={0.6}
          />
        );
      })}
      {visible.map((node) => {
        const pos = positions.get(node.label);
        if (!pos) return null;
        const r = NODE_R * (0.6 + node.weight * 0.6);
        return (
          <g key={node.label}>
            <circle
              cx={pos.x}
              cy={pos.y}
              r={r}
              fill={`rgba(37,99,235,${0.15 + node.weight * 0.4})`}
              stroke={node.is_core ? "#2563eb" : "#93c5fd"}
              strokeWidth={node.is_core ? 2 : 1}
            />
            <text
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={Math.max(8, Math.min(11, 200 / visible.length))}
              fill="#1e3a8a"
              fontWeight={node.is_core ? "bold" : "normal"}
              style={{ pointerEvents: "none" }}
            >
              {node.label.length > 12 ? node.label.slice(0, 11) + "…" : node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function PreferencesPage() {
  const [user, setUser] = useState<User | null>(null);
  const [graph, setGraph] = useState<InterestGraph | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.preferences.get().then(setUser).catch(() => {});
    api.preferences.interestGraph().then(setGraph).catch(() => {});
  }, []);

  const save = async () => {
    if (!user) return;
    setSaving(true);
    try {
      const updated = await api.preferences.update({
        digest_frequency: user.digest_frequency,
        digest_max_items: user.digest_max_items,
        serendipity_percentage: user.serendipity_percentage,
        timezone: user.timezone,
      });
      setUser(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {}
    setSaving(false);
  };

  if (!user) return <p style={{ color: "#6b7280" }}>Loading preferences...</p>;

  return (
    <div>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: 24 }}>Preferences</h1>

      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 16 }}>Digest Settings</h2>
        <div style={{ display: "grid", gap: 16, maxWidth: 480 }}>
          <div>
            <label style={{ display: "block", fontWeight: 500, marginBottom: 4 }}>Frequency</label>
            <select
              value={user.digest_frequency}
              onChange={(e) => setUser({ ...user, digest_frequency: e.target.value })}
              style={{ width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6 }}
            >
              <option value="daily">Daily</option>
              <option value="twice_daily">Twice daily</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 500, marginBottom: 4 }}>
              Max items per digest: {user.digest_max_items}
            </label>
            <input
              type="range"
              min={5}
              max={30}
              value={user.digest_max_items}
              onChange={(e) => setUser({ ...user, digest_max_items: Number(e.target.value) })}
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 500, marginBottom: 4 }}>
              Discovery percentage: {user.serendipity_percentage}%
            </label>
            <input
              type="range"
              min={0}
              max={50}
              value={user.serendipity_percentage}
              onChange={(e) => setUser({ ...user, serendipity_percentage: Number(e.target.value) })}
              style={{ width: "100%" }}
            />
            <p style={{ fontSize: 12, color: "#6b7280" }}>
              Percentage of digest items from outside your usual sources.
            </p>
          </div>
        </div>
        <button
          onClick={save}
          disabled={saving}
          style={{
            marginTop: 16,
            padding: "10px 24px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: saving ? "not-allowed" : "pointer",
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? "Saving..." : saved ? "Saved!" : "Save preferences"}
        </button>
      </section>

      {graph && (
        <section>
          <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 8 }}>Your Interest Graph</h2>
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 16 }}>
            Nodes = topics you engage with. Larger = higher weight. Bold border = core stable interest.
            Lines between nodes = topics you often read together.
          </p>

          {/* SVG graph visualization */}
          <InterestGraphSVG nodes={graph.nodes} edges={graph.edges} />

          {/* Tag cloud fallback */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
            {graph.nodes.slice(0, 30).map((node) => (
              <span
                key={node.label}
                style={{
                  padding: "4px 12px",
                  borderRadius: 20,
                  background: `rgba(37,99,235,${0.1 + node.weight * 0.5})`,
                  color: "#1e40af",
                  fontSize: `${0.75 + node.weight * 0.5}rem`,
                  fontWeight: node.is_core ? 700 : 400,
                  border: node.is_core ? "2px solid #93c5fd" : "1px solid #dbeafe",
                }}
              >
                {node.label}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
