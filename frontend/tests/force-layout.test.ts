import { describe, expect, it } from "vitest";
import { dropTarget, layout, radiusFor } from "../src/lib/forceLayout";

function graph(n: number) {
  const nodes = Array.from({ length: n }, (_, i) => ({ id: `t${i}`, radius: radiusFor(((i * 37) % 100) / 100) }));
  const edges = Array.from({ length: n }, (_, i) => ({ source: `t${i}`, target: `t${(i * 7 + 3) % n}`, weight: 0.5 }));
  return { nodes, edges };
}

describe("interest map layout (#179)", () => {
  it("lays out 200 nodes inside the box, quickly and deterministically", () => {
    const { nodes, edges } = graph(200);
    const start = performance.now();
    const pos = layout(nodes, edges, { width: 1000, height: 700 });
    const ms = performance.now() - start;
    expect(ms).toBeLessThan(1500); // one-off; well under a second on a laptop
    expect(pos.size).toBe(200);
    for (const node of nodes) {
      const p = pos.get(node.id)!;
      expect(p.x - node.radius).toBeGreaterThanOrEqual(-1);
      expect(p.x + node.radius).toBeLessThanOrEqual(1001);
      expect(p.y - node.radius).toBeGreaterThanOrEqual(-1);
      expect(p.y + node.radius).toBeLessThanOrEqual(701);
    }
    expect(layout(nodes, edges, { width: 1000, height: 700 })).toEqual(pos);
  });

  it("keeps nodes from overlapping, even with 200 of them", () => {
    const { nodes, edges } = graph(200);
    const pos = layout(nodes, edges);
    let overlaps = 0;
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++) {
        const a = pos.get(nodes[i].id)!, b = pos.get(nodes[j].id)!;
        if (Math.hypot(a.x - b.x, a.y - b.y) < (nodes[i].radius + nodes[j].radius) * 0.9) overlaps++;
      }
    expect(overlaps).toBeLessThanOrEqual(3);
  });

  it("finds the node a dragged node was dropped on", () => {
    const positions = new Map([["a", { x: 0, y: 0 }], ["b", { x: 100, y: 0 }], ["c", { x: 300, y: 0 }]]);
    const radii = new Map([["a", 10], ["b", 20], ["c", 10]]);
    expect(dropTarget("a", { x: 110, y: 5 }, positions, radii)).toBe("b");
    expect(dropTarget("a", { x: 200, y: 0 }, positions, radii)).toBeNull();
    expect(dropTarget("b", { x: 100, y: 0 }, positions, radii)).toBeNull(); // not itself
  });
});
