import { expect, test, type Page } from "@playwright/test";
import { insertArticle, signIn, sql } from "./stack";

// Reading telemetry end to end (#193): a real reader session in the browser
// must land as the right values in user_content_interactions.

async function readThrough(page: Page) {
  // Active reading: small mouse moves while scrolling down in steps.
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y <= height; y += 600) {
    await page.mouse.move(100 + (y % 300), 300);
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(250);
  }
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.mouse.move(400, 400);
  await page.waitForTimeout(800);
}

test("a full read lands as a completed interaction with real telemetry", async ({ page }) => {
  const email = await signIn(page);
  const itemId = insertArticle();

  await page.goto(`/read/${itemId}`);
  await expect(page.getByRole("heading", { name: "How compilers lower loops" })).toBeVisible();
  await readThrough(page);

  // The end of the article was reached: the post-read toast appears (#228).
  await expect(page.getByText(/You finished this in \d+ min/)).toBeVisible();

  // Hiding the tab flushes; closing it sends the keepalive beacon.
  const flushed = page.waitForResponse((r) => r.url().endsWith("/feedback/interaction") && r.ok());
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await flushed;
  await page.close({ runBeforeUnload: true });

  const row = sql(
    `SELECT i.reached_end, i.read_completion_pct, i.scroll_depth_pct, i.active_time_seconds, ` +
      `i.opened_at IS NOT NULL FROM user_content_interactions i JOIN users u ON u.id = i.user_id ` +
      `WHERE u.email = '${email}' AND i.content_item_id = '${itemId}'`,
  );
  const [reachedEnd, completion, scroll, active, opened] = row.split("|");
  expect(reachedEnd).toBe("t");
  expect(Number(completion)).toBeGreaterThanOrEqual(0.95);
  expect(Number(scroll)).toBeGreaterThanOrEqual(0.9);
  expect(Number(active)).toBeGreaterThanOrEqual(3);
  expect(opened).toBe("t");
});

test("a glance and leave is recorded as a bounce, not a read", async ({ page }) => {
  const email = await signIn(page);
  const itemId = insertArticle();

  await page.goto(`/read/${itemId}`);
  await expect(page.getByRole("heading", { name: "How compilers lower loops" })).toBeVisible();
  await page.mouse.move(200, 200);
  const flushed = page.waitForResponse((r) => r.url().endsWith("/feedback/interaction") && r.ok());
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await flushed;

  const row = sql(
    `SELECT coalesce(i.reached_end, false), coalesce(i.read_completion_pct, 0) FROM user_content_interactions i ` +
      `JOIN users u ON u.id = i.user_id WHERE u.email = '${email}' AND i.content_item_id = '${itemId}'`,
  );
  const [reachedEnd, completion] = row.split("|");
  expect(reachedEnd).toBe("f");
  expect(Number(completion)).toBeLessThan(0.5);
});
