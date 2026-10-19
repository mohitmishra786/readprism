import { expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

// Shared fixtures for the compose-stack e2e specs (#193, #216).
export const API = process.env.E2E_API_URL || "http://localhost:8000";
const COMPOSE_DIR = process.env.E2E_COMPOSE_DIR || path.resolve(__dirname, "../..");

export function sql(query: string): string {
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

// One account per run: registration is rate-limited (5/min per IP), so a
// fresh account per test would trip it on repeated local runs.
let account: { email: string; password: string } | null = null;

export async function signIn(page: Page): Promise<string> {
  if (!account) {
    account = { email: `e2e-${Date.now()}@example.com`, password: "E2e-Password-123!" };
    const reg = await page.request.post(`${API}/api/v1/auth/register`, { data: account });
    expect(reg.ok(), await reg.text()).toBeTruthy();
  }
  // Browser session: httpOnly cookies on the API host (#103).
  const login = await page.request.post(`${API}/api/v1/auth/login`, {
    data: account,
    headers: { "X-Auth-Mode": "cookie" },
  });
  expect(login.ok(), await login.text()).toBeTruthy();
  return account.email;
}

export function insertArticle(): string {
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


/**
 * The row a just-answered request wrote. The API's transaction can commit a
 * moment after the response is sent, so poll briefly instead of reading once.
 */
export async function sqlRow(query: string, timeoutMs = 10_000): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const row = sql(query);
    if (row || Date.now() > deadline) return row;
    await new Promise((r) => setTimeout(r, 250));
  }
}
