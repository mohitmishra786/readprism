import { defineConfig } from "@playwright/test";

/**
 * End-to-end against a real stack (#193): the compose backend (Postgres,
 * Redis, API) and a production frontend build. CI starts both; locally:
 *   docker compose -f docker-compose.yml -f docker-compose.build.yml up -d db redis backend
 *   NEXT_PUBLIC_API_URL=http://localhost:8000 npx next build && npx next start -p 3001
 *   npx playwright test -c playwright.stack.config.ts
 */
export default defineConfig({
  testDir: "./e2e-stack",
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: { baseURL: process.env.E2E_BASE_URL || "http://localhost:3001", trace: "off" },
  reporter: [["list"]],
});
