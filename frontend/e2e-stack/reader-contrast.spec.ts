import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { insertArticle, signIn } from "./stack";

// The article must be readable on every reading surface, whatever the OS
// colour scheme (#316): it used to be near-black on near-black in dark mode.
const axeSource = readFileSync("node_modules/axe-core/axe.min.js", "utf8");

for (const scheme of ["light", "dark"] as const) {
  for (const surface of ["light", "sepia", "dark"] as const) {
    test(`reader text contrast: OS ${scheme}, ${surface} surface`, async ({ browser }) => {
      const context = await browser.newContext({ colorScheme: scheme, reducedMotion: "reduce" });
      await context.addInitScript((s) => localStorage.setItem("reader-theme", s), surface);
      const page = await context.newPage();
      await signIn(page);
      const itemId = insertArticle();
      await page.goto(`/read/${itemId}`);
      await expect(page.getByText(/Paragraph 1\./)).toBeVisible();

      await page.evaluate(axeSource);
      const failures = await page.evaluate(async () => {
        // @ts-expect-error injected axe global
        const result = await window.axe.run(document, { runOnly: ["color-contrast"] });
        return result.violations.flatMap((v: { nodes: { target: string[]; failureSummary: string }[] }) =>
          v.nodes.map((n) => `${n.target.join(" ")}: ${n.failureSummary.replace(/\s+/g, " ").slice(0, 140)}`),
        );
      });
      expect(failures, failures.join("\n")).toEqual([]);
      await context.close();
    });
  }
}
