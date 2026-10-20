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

// Hide one-off notices so the shots show the product, not the welcome banner
// and calibration questions. Clicking dismiss is what a reader would do.
async function clearDigestChrome(page: Page) {
  const prompts = page.getByRole("button", { name: /^Dismiss prompt:/ });
  // The calibration questions load after the cards; wait for them (or not).
  await prompts.first().waitFor({ state: "visible", timeout: 5000 }).catch(() => {});
  while ((await prompts.count()) > 0) {
    await prompts.first().click();
    await page.waitForTimeout(150); // let the list re-render
  }
  const banner = page.getByRole("button", { name: "Dismiss", exact: true });
  if ((await banner.count()) > 0) await banner.first().click();
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function shoot(page: Page, file: string) {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: file, animations: "disabled" });
  optimizeSize(file);
}

async function capture() {
  const theme = "dark"; // the app has one look (#159)
  console.log(`\n=== Capturing screenshots for theme: ${theme} ===`);
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    colorScheme: theme,
    // The app honours reduced motion, so cards don't get caught mid fade-in.
    reducedMotion: "reduce",
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
  await clearDigestChrome(page);

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
  const digestPath = path.join(OUT_DIR, `digest.png`);
  await shoot(page, digestPath);
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
  const whyThisPath = path.join(OUT_DIR, `why-this.png`);
  await shoot(page, whyThisPath);
  console.log(`Saved ${whyThisPath}`);

  // Shot 3: interests
  console.log("Capturing interests...");
  await page.goto(`${BASE_URL}/interests`, { waitUntil: "networkidle" });
  await page.locator('h1:has-text("Interests")').waitFor({ state: "visible", timeout: 10000 });
  await page.locator("svg").first().waitFor({ state: "visible", timeout: 10000 });
  await page.locator('text="All topics"').first().waitFor({ state: "visible", timeout: 10000 });
  await assertAuthenticatedAndValid(page, "interests");
  const interestsPath = path.join(OUT_DIR, `interests.png`);
  await shoot(page, interestsPath);
  console.log(`Saved ${interestsPath}`);

  // Shot 4: reader
  console.log(`Capturing reader for article ${firstArticleId}...`);
  await page.evaluate(() => window.localStorage.removeItem("reader-theme"));
  await page.goto(`${BASE_URL}/read/${firstArticleId}`, { waitUntil: "networkidle" });
  await page.locator(".prose-reader").waitFor({ state: "visible", timeout: 10000 });
  await page.locator("header h1").waitFor({ state: "visible", timeout: 10000 });
  await assertAuthenticatedAndValid(page, "reader");
  const readerPath = path.join(OUT_DIR, `reader.png`);
  await shoot(page, readerPath);
  console.log(`Saved ${readerPath}`);

  // Shot 5: sources
  console.log("Capturing sources...");
  await page.goto(`${BASE_URL}/sources`, { waitUntil: "networkidle" });
  await page.locator('h1:has-text("Sources")').waitFor({ state: "visible", timeout: 10000 });
  await page.locator(".card").first().waitFor({ state: "visible", timeout: 10000 });
  await assertAuthenticatedAndValid(page, "sources");
  const sourcesPath = path.join(OUT_DIR, `sources.png`);
  await shoot(page, sourcesPath);
  console.log(`Saved ${sourcesPath}`);

  await context.close();
  await browser.close();
}

async function main() {
  if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
  }

  await capture();

  console.log("\nAll 5 screenshots captured successfully!");
}

main().catch((err) => {
  console.error("Screenshot capture failed:", err);
  process.exit(1);
});
