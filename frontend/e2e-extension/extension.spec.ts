import { chromium, expect, test, type BrowserContext, type Page, type Worker } from "@playwright/test";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";

// The spec drives the extension's own APIs inside the browser; their types
// are not needed for that, so keep the dependency list small.
declare const chrome: any;

// The extension's pre-granted origin is http://localhost:8000 (#214); the
// stub plays the ReadPrism API there and serves a page with a feed link.
const API_PORT = 8000;
const OTHER_PORT = 4568; // an origin the extension has no access to
const EXTENSION = path.resolve(__dirname, "../../extension");
const TOKEN = "rp_e2e_token";

type Call = { method: string; path: string; auth?: string; body: unknown };

function page(feedHref: string) {
  return `<!doctype html><html><head><title>A post about compilers</title>
<link rel="alternate" type="application/rss+xml" href="${feedHref}"></head>
<body><h1>A post about compilers</h1></body></html>`;
}

function startServer(port: number, calls: Call[]): Promise<http.Server> {
  const server = http.createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      const url = req.url || "/";
      if (req.method === "OPTIONS") {
        res.writeHead(204, {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "Authorization, Content-Type",
          "Access-Control-Allow-Methods": "POST, GET",
        });
        return res.end();
      }
      if (url === "/article") {
        res.writeHead(200, { "Content-Type": "text/html" });
        return res.end(page("/feed.xml"));
      }
      if (url.startsWith("/api/v1/")) {
        calls.push({
          method: req.method || "",
          path: url,
          auth: req.headers.authorization,
          body: raw ? JSON.parse(raw) : null,
        });
        res.writeHead(200, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
        return res.end(JSON.stringify({ name: "Feed", status: "ok" }));
      }
      res.writeHead(404);
      res.end();
    });
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve(server)));
}

let context: BrowserContext;
let worker: Worker;
let extensionId: string;
const calls: Call[] = [];
const servers: http.Server[] = [];

test.beforeAll(async () => {
  servers.push(await startServer(API_PORT, calls), await startServer(OTHER_PORT, []));
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "rp-ext-"));
  context = await chromium.launchPersistentContext(userData, {
    channel: "chromium", // the new headless mode, which can load extensions
    args: [`--disable-extensions-except=${EXTENSION}`, `--load-extension=${EXTENSION}`],
  });
  worker = context.serviceWorkers()[0] ?? (await context.waitForEvent("serviceworker"));
  extensionId = worker.url().split("/")[2];
  await worker.evaluate((token) => chrome.storage.local.set({ token }), TOKEN);
});

test.afterAll(async () => {
  await context?.close();
  for (const s of servers) s.close();
});

/**
 * Open the popup as a page. A real popup's "active tab" is the page behind
 * it; here the popup is its own tab, so point chrome.tabs.query at the
 * article tab the way the browser would.
 */
async function openPopupFor(articleUrl: string): Promise<Page> {
  const tab = await worker.evaluate(
    async (url) => (await chrome.tabs.query({ url }))[0],
    articleUrl,
  );
  const popup = await context.newPage();
  await popup.addInitScript((activeTab) => {
    const original = chrome.tabs.query.bind(chrome.tabs);
    chrome.tabs.query = (info: { active?: boolean }) =>
      info.active ? Promise.resolve([activeTab]) : original(info);
  }, tab);
  await popup.goto(`chrome-extension://${extensionId}/popup.html`);
  return popup;
}

test("detects the page's feed on click and subscribes to it", async () => {
  const article = await context.newPage();
  await article.goto(`http://localhost:${API_PORT}/article`);
  const popup = await openPopupFor(`http://localhost:${API_PORT}/article`);

  const subscribe = popup.getByRole("button", { name: "Subscribe to detected feed" });
  await expect(subscribe).toBeVisible();
  await expect(subscribe).toHaveAttribute("title", `http://localhost:${API_PORT}/feed.xml`);
  await subscribe.click();
  await expect(popup.locator("#status")).toHaveText(/Feed/);
  const add = calls.find((c) => c.path === "/api/v1/sources");
  expect(add?.body).toEqual({ url: `http://localhost:${API_PORT}/feed.xml` });
  expect(add?.auth).toBe(`Bearer ${TOKEN}`);
});

test("saves and rates the current page", async () => {
  const article = await context.newPage();
  await article.goto(`http://localhost:${API_PORT}/article`);
  const popup = await openPopupFor(`http://localhost:${API_PORT}/article`);

  await popup.getByRole("button", { name: /Save & rate up/ }).click();
  await expect(popup.locator("#status")).toHaveText("Saved helpful");
  const save = calls.find((c) => c.path === "/api/v1/extension/save");
  expect(save?.body).toEqual({
    url: `http://localhost:${API_PORT}/article`,
    title: "A post about compilers",
    rating: 1,
  });
  expect(save?.auth).toBe(`Bearer ${TOKEN}`);
});

test("does not read pages it was not granted (#214)", async () => {
  // Without a user click on the extension (activeTab) and with no host
  // permission for this origin, detection cannot run, so no feed is offered.
  const article = await context.newPage();
  await article.goto(`http://127.0.0.1:${OTHER_PORT}/article`);
  const popup = await openPopupFor(`http://127.0.0.1:${OTHER_PORT}/article`);
  await popup.waitForTimeout(1000);
  await expect(popup.getByRole("button", { name: "Subscribe to detected feed" })).toBeHidden();
});
