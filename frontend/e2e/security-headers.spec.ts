import { expect, test } from "@playwright/test";

/**
 * #187: the CSP and security headers apply to every document route, not just
 * /read. Asserts the securityheaders-style headers and that the pages hydrate
 * without CSP violations (no console errors mentioning the policy).
 */

const ROUTES = ["/", "/login", "/how-it-works"];

test("security headers on every page", async ({ page }) => {
  for (const path of ROUTES) {
    const resp = await page.goto(path);
    const headers = resp?.headers() ?? {};
    expect(headers["content-security-policy"], path).toContain("'strict-dynamic'");
    expect(headers["content-security-policy"], path).toContain("frame-ancestors 'none'");
    expect(headers["x-content-type-options"], path).toBe("nosniff");
    expect(headers["referrer-policy"], path).toBe("strict-origin-when-cross-origin");
    expect(headers["permissions-policy"], path).toContain("camera=()");
  }
});

test("pages hydrate without CSP violations", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" && /Content Security Policy|csp/i.test(msg.text())) {
      violations.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    if (/Content Security Policy|csp/i.test(String(err))) {
      violations.push(String(err));
    }
  });
  for (const path of ROUTES) {
    await page.goto(path);
    await expect(page.locator("body")).toBeVisible();
  }
  expect(violations, violations.join("; ")).toHaveLength(0);
});
