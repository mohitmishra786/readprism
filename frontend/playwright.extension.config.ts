import { defineConfig } from "@playwright/test";

/**
 * Browser e2e for the MV3 extension (#215): loads extension/ unpacked into
 * Chromium and talks to a stub ReadPrism API started by the spec. No Next
 * server needed.
 */
export default defineConfig({
  testDir: "./e2e-extension",
  timeout: 45_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
});
