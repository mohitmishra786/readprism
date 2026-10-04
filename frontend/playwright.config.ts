import { defineConfig, devices } from "@playwright/test";

/**
 * E2E + a11y pipeline (D-15). Runs against a production build served by
 * `next start` with the API pointed at a stub (the specs under test do not
 * need a live backend; API-dependent flows stay out until a compose-based
 * e2e job exists).
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  reporter: [["list"]],
});
