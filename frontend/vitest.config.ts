import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    // Unit and component tests. Component tests opt into a DOM with a
    // `// @vitest-environment jsdom` header. Playwright specs live in e2e/
    // and run via `npm run e2e`.
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
    setupFiles: ["tests/setup.ts"],
  },
});
