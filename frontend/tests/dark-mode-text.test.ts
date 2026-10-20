import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Near-black text with no dark variant is invisible on the dark background
// (source names and section headings were, #159 screenshots).
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : path.endsWith(".tsx") ? [path] : [];
  });
}

describe("dark mode text", () => {
  it("every text-stone-900 has a dark: text colour (unless on a fixed light surface)", () => {
    const offenders: string[] = [];
    for (const file of files(join(__dirname, "../src"))) {
      for (const match of readFileSync(file, "utf8").matchAll(/className="([^"]*)"/g)) {
        const cls = match[1];
        if (!/\btext-stone-900\b/.test(cls) || /dark:text-/.test(cls)) continue;
        if (/\bbg-(white|stone-50)\b/.test(cls)) continue;
        offenders.push(`${file}: ${cls}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
