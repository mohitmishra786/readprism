import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Digest email in a real browser engine (#217): the snapshot rendered by the
// backend template, at desktop and phone widths and in dark mode. This is a
// proxy for mail clients (Apple Mail is WebKit; Gmail/Outlook web are
// Chromium-based), not a substitute for checking real inboxes.
const SNAPSHOT = path.resolve(__dirname, "../../backend/tests/fixtures/email/digest_email.html");
const html = fs.readFileSync(SNAPSHOT, "utf8");

const cases = [
  { name: "desktop-light", width: 900, scheme: "light" as const },
  { name: "phone-light", width: 375, scheme: "light" as const },
  { name: "phone-dark", width: 375, scheme: "dark" as const },
];

for (const c of cases) {
  test(`digest email renders cleanly: ${c.name}`, async ({ page }, info) => {
    await page.setViewportSize({ width: c.width, height: 900 });
    await page.emulateMedia({ colorScheme: c.scheme });
    await page.setContent(html);

    // No sideways scrolling on a phone.
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);

    // Every item keeps its read/rate/save actions, visible and tappable.
    await expect(page.getByRole("link", { name: "Read in Weirling" })).toHaveCount(4);
    const button = page.getByRole("link", { name: "Useful" }).first();
    await expect(button).toBeVisible();
    const box = await button.boundingBox();
    expect(box && box.height).toBeGreaterThanOrEqual(24);

    // Dark mode actually darkens the page and keeps text readable.
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    const title = await page.getByRole("link", { name: "How compilers lower loops" }).evaluate(
      (el) => getComputedStyle(el).color,
    );
    if (c.scheme === "dark") {
      expect(bg).toBe("rgb(12, 10, 9)");
      expect(title).toBe("rgb(245, 245, 244)");
    } else {
      expect(bg).toBe("rgb(245, 245, 244)");
    }

    await page.screenshot({ path: info.outputPath(`${c.name}.png`), fullPage: true });
  });
}
