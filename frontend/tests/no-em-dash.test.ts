import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory()
      ? walk(full)
      : full.endsWith(".ts") || full.endsWith(".tsx")
        ? [full]
        : [];
  });
}

function stripComments(source: string): string {
  // Strip JSX comments: {/* ... */}
  let clean = source.replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "");
  // Strip block comments: /* ... */
  clean = clean.replace(/\/\*[\s\S]*?\*\//g, "");
  // Strip line comments: // ... (avoid matching :// in URLs)
  clean = clean.replace(/(^|[^:])\/\/.*$/gm, "$1");
  return clean;
}

describe("No em or en dashes in user-facing frontend code", () => {
  it("frontend/src has zero em dashes (—) or en dashes (–) in code, strings, or JSX", () => {
    const srcDir = join(__dirname, "../src");
    const files = walk(srcDir);
    const offenders: string[] = [];

    for (const file of files) {
      const content = readFileSync(file, "utf8");
      const stripped = stripComments(content);
      const lines = stripped.split("\n");
      for (let idx = 0; idx < lines.length; idx++) {
        const line = lines[idx];
        if (line.includes("—") || line.includes("–")) {
          offenders.push(`${file}:${idx + 1}: ${line.trim()}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it("public/manifest.json and public/sw.js have zero em dashes (—) or en dashes (–)", () => {
    const publicDir = join(__dirname, "../public");
    const targets = [join(publicDir, "manifest.json"), join(publicDir, "sw.js")];
    const offenders: string[] = [];

    for (const file of targets) {
      const content = readFileSync(file, "utf8");
      const stripped = stripComments(content);
      const lines = stripped.split("\n");
      for (let idx = 0; idx < lines.length; idx++) {
        const line = lines[idx];
        if (line.includes("—") || line.includes("–")) {
          offenders.push(`${file}:${idx + 1}: ${line.trim()}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});
