import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Unit tests only — Playwright specs live in e2e/ and run via `npm run e2e`.
    include: ["tests/**/*.test.ts"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
