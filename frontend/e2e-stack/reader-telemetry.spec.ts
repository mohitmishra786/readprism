import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

// Reading telemetry end to end (#193): a real reader session in the browser
// must land as the right values in user_content_interactions.
const API = process.env.E2E_API_URL || "http://localhost:8000";
const COMPOSE_DIR = process.env.E2E_COMPOSE_DIR || path.resolve(__dirname, "../..");

function sql(query: string): string {
  return execFileSync(
    "docker",
    ["compose", "exec", "-T", "db", "psql", "-U", "readprism", "-d", "readprism", "-tA", "-c", query],
    { cwd: COMPOSE_DIR, encoding: "utf8" },
  ).trim();
}

function article(): string {
  const para =
    "Compilers lower loops into simpler control flow, then schedule instructions " +
    "so the processor stays busy. Each pass keeps the program's meaning while making " +
    "it cheaper to run, and the order of passes matters as much as the passes themselves.";
  return Array.from({ length: 60 }, (_, i) => `Paragraph ${i + 1}. ${para}`).join("\n\n");
}

async function signIn(page: Page): Promise<string> {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "E2e-Password-123!";
  const reg = await page.request.post(`${API}/api/v1/auth/register`, { data: { email, password } });
  expect(reg.ok(), await reg.text()).toBeTruthy();
  // Browser session: httpOnly cookies on the API host (#103).
  const login = await page.request.post(`${API}/api/v1/auth/login`, {
    data: { email, password },
    headers: { "X-Auth-Mode": "cookie" },
  });
  expect(login.ok()).toBeTruthy();
  return email;
}

function insertArticle(): string {
  const text = article().replace(/'/g, "''");
  return sql(
    `INSERT INTO content_items (id, url, title, full_text, word_count, reading_time_minutes, ` +
      `topic_clusters, extraction_method, fetched_at, rankable, paywalled, origin, ` +
      `has_citations, summarization_cached) VALUES ` +
      `(gen_random_uuid(), 'https://e2e.example/${Date.now()}', 'How compilers lower loops', ` +
      `'${text}', 2400, 1, '["compilers"]'::jsonb, 'feed', now(), true, false, 'followed', ` +
      `false, false) RETURNING id`,
  ).split("\n")[0];
}

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
