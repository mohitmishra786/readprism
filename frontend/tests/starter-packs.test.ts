import { describe, expect, it } from "vitest";
import { packSummary } from "../src/components/sources/StarterPackPicker";
import type { StarterPack } from "../src/lib/types";

const pack = (id: string, feed_count: number): StarterPack => ({
  id,
  title: id,
  feed_count,
  feeds: [],
  suggested: false,
  subscribed: 0,
});

describe("starter pack picker (#152)", () => {
  it("summarises the selection for the sticky footer", () => {
    const packs = [pack("a", 10), pack("b", 21), pack("c", 5)];
    expect(packSummary(packs, ["a", "b"])).toBe("2 packs · 31 sources");
    expect(packSummary(packs, ["c"])).toBe("1 pack · 5 sources");
    expect(packSummary(packs, [])).toBe("0 packs · 0 sources");
  });
});
