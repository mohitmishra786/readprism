import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

/**
 * D-15 pipeline: real-browser smoke + axe a11y (0 serious) + PWA surface.
 * The marketing pages render without auth, so they carry the a11y gate;
 * app pages redirect to /login, which is also scanned.
 */

async function injectAxe(page: import("@playwright/test").Page) {
  const axeSource = readFileSync("node_modules/axe-core/axe.min.js", "utf8");
  await page.addScriptTag({ content: axeSource });
}

interface AxeResults {
  violations: Array<{ id: string; impact: string | null; nodes: unknown[] }>;
}

async function axeViolations(page: import("@playwright/test").Page): Promise<AxeResults> {
  return page.evaluate(() => {
    const axe = (window as unknown as { axe: { run: () => Promise<AxeResults> } }).axe;
    return axe.run();
  });
}

test("home page renders and has no serious axe violations", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/ReadPrism/i);
  await injectAxe(page);
  const results = await axeViolations(page);
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  const summary = serious.map((v) => `${v.id}(${v.impact}): ${v.nodes.length} nodes`);
  expect(serious, summary.join("; ")).toHaveLength(0);
});

test("login page has no serious axe violations", async ({ page }) => {
  await page.goto("/login");
  await injectAxe(page);
  const results = await axeViolations(page);
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(
    serious,
    JSON.stringify(serious.map((v) => v.id)),
  ).toHaveLength(0);
});

test("PWA surface: manifest and service worker are served", async ({ request }) => {
  const manifest = await request.get("/manifest.json");
  expect(manifest.ok()).toBeTruthy();
  const body = await manifest.json();
  expect(body.name).toBe("ReadPrism");
  expect(body.icons.length).toBeGreaterThan(0);

  const sw = await request.get("/sw.js");
  expect(sw.ok()).toBeTruthy();
  const swText = await sw.text();
  expect(sw.headers()["content-type"]).toContain("javascript");
  // Offline digest/reader caching branch exists (EC-01).
  expect(swText).toContain("digest/latest");
});
