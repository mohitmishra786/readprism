import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// #168: comparison claims go stale; each page must say when it was checked
// and link its sources, and use our real prices from one place.
const VS = join(__dirname, "../src/app/vs");

describe("/vs pages", () => {
  const pages = readdirSync(VS);

  it("covers the competitors the product plan names", () => {
    expect([...pages].sort()).toEqual(["feedly", "folo", "inoreader", "newsblur", "readless"]);
  });

  it.each(pages)("%s has a checked date, https sources and shared pricing", (slug) => {
    const src = readFileSync(join(VS, slug, "page.tsx"), "utf8");
    expect(src).toMatch(/checked: "[A-Z][a-z]+ \d{1,2}, 20\d\d"/);
    expect(src).toMatch(/url: "https:\/\//);
    expect(src).toContain("WEIRLING_PRICING");
    expect(src).not.toContain("$4.99");
  });
});
