import { chromium, type Page } from "@playwright/test";
import { execSync } from "child_process";
import fs from "fs";
import path from "path";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";
const DEMO_EMAIL = process.env.DEMO_EMAIL;
const DEMO_PASSWORD = process.env.DEMO_PASSWORD;

if (!DEMO_EMAIL || !DEMO_PASSWORD) {
  console.error("Error: DEMO_EMAIL and DEMO_PASSWORD environment variables are required.");
  process.exit(1);
}

const OUT_DIR = path.resolve(__dirname, "../../docs/media");

async function assertAuthenticatedAndValid(page: Page, stepName: string) {
  const url = page.url();
  if (url.includes("/login")) {
    throw new Error(`[${stepName}] Assertion failed: URL is login page (${url})`);
  }
  const signInButtons = await page.getByRole("button", { name: "Sign in" }).count();
  if (signInButtons > 0) {
    throw new Error(`[${stepName}] Assertion failed: 'Sign in' button found on page (${url})`);
  }
}

function optimizeSize(filePath: string) {
  const maxBytes = 300 * 1024;
  let stats = fs.statSync(filePath);
  if (stats.size > maxBytes) {
    console.log(`Optimizing ${path.basename(filePath)} (${Math.round(stats.size / 1024)} KB > 300 KB)...`);
    try {
      execSync(`pngquant --quality 70-90 --force --output "${filePath}" "${filePath}"`);
      stats = fs.statSync(filePath);
      console.log(`Recompressed ${path.basename(filePath)} to ${Math.round(stats.size / 1024)} KB`);
    } catch (err) {
      console.warn(`pngquant failed on ${filePath}:`, err);
    }
  }
  if (stats.size > maxBytes) {
    throw new Error(`Screenshot ${path.basename(filePath)} is ${Math.round(stats.size / 1024)} KB, exceeding 300 KB limit.`);
  }
}

async function captureForTheme(theme: "light" | "dark") {
  console.log(`\n=== Capturing screenshots for theme: ${theme} ===`);
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    colorScheme: theme,
  });

  const page = await context.newPage();

  // 1. Sign in
  console.log(`Navigating to ${BASE_URL}/login...`);
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle" });
  await page.locator("#login-email").fill(DEMO_EMAIL!);
  await page.locator("#login-password").fill(DEMO_PASSWORD!);
  await page.locator('button[type="submit"]:has-text("Sign in")').click();

  console.log("Waiting for /digest and digest cards...");
  await page.waitForURL(/\/digest/, { timeout: 15000 });
  await page.locator("article.card").first().waitFor({ state: "visible", timeout: 15000 });
  await page.locator('h1:has-text("Your Digest")').waitFor({ state: "visible", timeout: 15000 });
  await page.waitForLoadState("networkidle");

  // Get first article ID for reader view
  const firstArticleLink = await page.locator('article.card h3 a[href^="/read/"]').first().getAttribute("href");
  if (!firstArticleLink) {
    throw new Error("Could not find article ID on first digest card");
  }
  const firstArticleId = firstArticleLink.replace("/read/", "");
  console.log(`Found first digest article ID: ${firstArticleId}`);

  // Shot 1: digest
  console.log("Capturing digest...");
  await assertAuthenticatedAndValid(page, "digest");
  const digestPath = path.join(OUT_DIR, `digest-${theme}.png`);
  await page.screenshot({ path: digestPath });
  optimizeSize(digestPath);
  console.log(`Saved ${digestPath}`);

  // Shot 2: why-this
  console.log("Capturing why-this...");
  const firstCard = page.locator("article.card").first();
  await firstCard.scrollIntoViewIfNeeded();
  const whyBtn = firstCard.locator('button:has-text("Why this?")');
  await whyBtn.waitFor({ state: "visible", timeout: 10000 });
  await whyBtn.click();
  const whyPanel = page.locator('text="Why this is ranked here"').first();
  await whyPanel.waitFor({ state: "visible", timeout: 10000 });
  await assertAuthenticatedAndValid(page, "why-this");
  const whyThisPath = path.join(OUT_DIR, `why-this-${theme}.png`);
  await page.screenshot({ path: whyThisPath });
  optimizeSize(whyThisPath);
  console.log(`Saved ${whyThisPath}`);

  // Shot 3: interests
  console.log("Capturing interests...");
  await page.goto(`${BASE_URL}/interests`, { waitUntil: "networkidle" });
  await page.locator('h1:has-text("Interests")').waitFor({ state: "visible", timeout: 10000 });
  await page.locator("svg").first().waitFor({ state: "visible", timeout: 10000 });
  await page.locator('text="All topics"').first().waitFor({ state: "visible", timeout: 10000 });
  await assertAuthenticatedAndValid(page, "interests");
  const interestsPath = path.join(OUT_DIR, `interests-${theme}.png`);
  await page.screenshot({ path: interestsPath });
  optimizeSize(interestsPath);
  console.log(`Saved ${interestsPath}`);

  // Shot 4: reader
  console.log(`Capturing reader for article ${firstArticleId}...`);
  if (theme === "dark") {
    await page.evaluate(() => window.localStorage.setItem("reader-theme", "dark"));
  } else {
    await page.evaluate(() => window.localStorage.setItem("reader-theme", "light"));
  }
  await page.goto(`${BASE_URL}/read/${firstArticleId}`, { waitUntil: "networkidle" });
  await page.locator(".prose-reader").waitFor({ state: "visible", timeout: 10000 });
  await page.locator("header h1").waitFor({ state: "visible", timeout: 10000 });
  await assertAuthenticatedAndValid(page, "reader");
  const readerPath = path.join(OUT_DIR, `reader-${theme}.png`);
  await page.screenshot({ path: readerPath });
  optimizeSize(readerPath);
  console.log(`Saved ${readerPath}`);

  // Shot 5: sources
  console.log("Capturing sources...");
  await page.goto(`${BASE_URL}/sources`, { waitUntil: "networkidle" });
  await page.locator('h1:has-text("Sources")').waitFor({ state: "visible", timeout: 10000 });
  await page.locator(".card").first().waitFor({ state: "visible", timeout: 10000 });
  await assertAuthenticatedAndValid(page, "sources");
  const sourcesPath = path.join(OUT_DIR, `sources-${theme}.png`);
  await page.screenshot({ path: sourcesPath });
  optimizeSize(sourcesPath);
  console.log(`Saved ${sourcesPath}`);

  await context.close();
  await browser.close();
}

async function main() {
  if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
  }

  await captureForTheme("light");
  await captureForTheme("dark");

  console.log("\nAll 10 screenshots captured successfully!");
}

main().catch((err) => {
  console.error("Screenshot capture failed:", err);
  process.exit(1);
});
