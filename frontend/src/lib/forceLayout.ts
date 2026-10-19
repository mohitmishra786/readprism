// Force-directed layout for the interest map (#179). Computed once (not a
// per-frame simulation) so 200+ nodes stay smooth on a phone: repulsion
// between every pair, springs along "read together" edges, a gentle pull
// to the centre, and cooling. Deterministic for a given input.

export interface LayoutNode {
  id: string;
  radius: number;
}
export interface LayoutEdge {
  source: string;
  target: string;
  weight: number;
}
export interface Point {
  x: number;
  y: number;
}

function seeded(seed: number): () => number {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 100000) / 100000;
  };
}

export function layout(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  { width = 1000, height = 700, iterations = 260 }: { width?: number; height?: number; iterations?: number } = {},
): Map<string, Point> {
  const n = nodes.length;
  const index = new Map(nodes.map((node, i) => [node.id, i]));
  const rand = seeded(n * 7919 + edges.length);
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  // Start on a spiral so nodes never coincide.
  for (let i = 0; i < n; i++) {
    const a = i * 2.399963 + rand() * 0.1;
    const r = 20 * Math.sqrt(i + 1);
    x[i] = Math.cos(a) * r;
    y[i] = Math.sin(a) * r;
  }
  const springs = edges
    .map((e) => [index.get(e.source), index.get(e.target), e.weight] as const)
    .filter(([a, b]) => a !== undefined && b !== undefined && a !== b) as [number, number, number][];

  const area = width * height;
  const k = Math.sqrt(area / Math.max(n, 1)) * 0.55; // ideal spacing
  let temperature = width / 8;
  const dx = new Float64Array(n);
  const dy = new Float64Array(n);
  for (let it = 0; it < iterations; it++) {
    dx.fill(0);
    dy.fill(0);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let ddx = x[i] - x[j];
        let ddy = y[i] - y[j];
        let dist2 = ddx * ddx + ddy * ddy;
        if (dist2 < 0.01) {
          ddx = rand() - 0.5;
          ddy = rand() - 0.5;
          dist2 = 0.01;
        }
        const minGap = nodes[i].radius + nodes[j].radius + 6;
        const force = (k * k) / dist2 + (dist2 < minGap * minGap ? 2 : 0);
        dx[i] += ddx * force;
        dy[i] += ddy * force;
        dx[j] -= ddx * force;
        dy[j] -= ddy * force;
      }
    }
    for (const [a, b, w] of springs) {
      const ddx = x[a] - x[b];
      const ddy = y[a] - y[b];
      const dist = Math.sqrt(ddx * ddx + ddy * ddy) || 0.01;
      const force = (dist / k) * (0.3 + Math.min(1, w));
      dx[a] -= (ddx / dist) * force * dist * 0.05;
      dy[a] -= (ddy / dist) * force * dist * 0.05;
      dx[b] += (ddx / dist) * force * dist * 0.05;
      dy[b] += (ddy / dist) * force * dist * 0.05;
    }
    for (let i = 0; i < n; i++) {
      dx[i] -= x[i] * 0.02; // gravity
      dy[i] -= y[i] * 0.02;
      const len = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      const step = Math.min(len, temperature);
      x[i] += (dx[i] / len) * step;
      y[i] += (dy[i] / len) * step;
    }
    temperature *= 0.975;
  }

  // Fit into the box with a margin.
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < n; i++) {
    minX = Math.min(minX, x[i] - nodes[i].radius);
    maxX = Math.max(maxX, x[i] + nodes[i].radius);
    minY = Math.min(minY, y[i] - nodes[i].radius);
    maxY = Math.max(maxY, y[i] + nodes[i].radius);
  }
  const margin = 40;
  const scale = Math.min(
    (width - 2 * margin) / Math.max(maxX - minX, 1),
    (height - 2 * margin) / Math.max(maxY - minY, 1),
    1.5,
  );
  for (let i = 0; i < n; i++) {
    x[i] = margin + (x[i] - minX) * scale + (width - 2 * margin - (maxX - minX) * scale) / 2;
    y[i] = margin + (y[i] - minY) * scale + (height - 2 * margin - (maxY - minY) * scale) / 2;
  }
  // Fitting shrinks distances but not radii: push overlapping circles apart
  // in screen space, staying inside the box.
  for (let pass = 0; pass < 60; pass++) {
    let moved = false;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const ddx = x[j] - x[i];
        const ddy = y[j] - y[i];
        const dist = Math.sqrt(ddx * ddx + ddy * ddy) || 0.01;
        const gap = nodes[i].radius + nodes[j].radius + 2 - dist;
        if (gap > 0) {
          const ux = ddx / dist, uy = ddy / dist;
          x[i] -= ux * gap * 0.5;
          y[i] -= uy * gap * 0.5;
          x[j] += ux * gap * 0.5;
          y[j] += uy * gap * 0.5;
          moved = true;
        }
      }
    }
    for (let i = 0; i < n; i++) {
      const r = nodes[i].radius;
      x[i] = Math.min(width - r, Math.max(r, x[i]));
      y[i] = Math.min(height - r, Math.max(r, y[i]));
    }
    if (!moved) break;
  }
  const out = new Map<string, Point>();
  for (let i = 0; i < n; i++) out.set(nodes[i].id, { x: x[i], y: y[i] });
  return out;
}

/** Node radius from interest weight (0..1). */
export function radiusFor(weight: number): number {
  return 6 + Math.max(0, Math.min(1, weight)) * 22;
}

/** The node under a dropped node, if they overlap: drag-to-merge (#179). */
export function dropTarget(
  dragged: string,
  at: Point,
  positions: Map<string, Point>,
  radii: Map<string, number>,
): string | null {
  let best: string | null = null;
  let bestDist = Infinity;
  for (const [id, p] of positions) {
    if (id === dragged) continue;
    const d = Math.hypot(p.x - at.x, p.y - at.y);
    if (d <= (radii.get(id) ?? 0) + 8 && d < bestDist) {
      best = id;
      bestDist = d;
    }
  }
  return best;
}
