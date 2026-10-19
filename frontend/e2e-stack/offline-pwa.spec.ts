import { expect, test } from "@playwright/test";
import { insertArticle, signIn } from "./stack";

// Offline reading (#216): once the service worker controls the app, an
// article read online stays readable with the network gone.
test("an opened article is readable offline", async ({ page, context }) => {
  await signIn(page);
  const itemId = insertArticle();

  await page.goto(`/read/${itemId}`);
  await expect(page.getByRole("heading", { name: "How compilers lower loops" })).toBeVisible();
  // First visit installs the worker; wait until it controls the page, then
  // read once more so the navigation, assets and article response go
  // through it and land in its cache.
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise((r) => navigator.serviceWorker.addEventListener("controllerchange", r, { once: true }));
    }
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "How compilers lower loops" })).toBeVisible();
  await expect(page.getByText(/Paragraph 60\./)).toBeVisible();
  // The article response must be in the worker's cache before going offline.
  await expect
    .poll(() =>
      page.evaluate(async (id) => {
        for (const name of await caches.keys()) {
          for (const req of await (await caches.open(name)).keys()) {
            if (req.url.endsWith(`/api/v1/content/${id}`)) return true;
          }
        }
        return false;
      }, itemId),
    )
    .toBe(true);

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: "How compilers lower loops" })).toBeVisible();
  await expect(page.getByText(/Paragraph 1\./)).toBeVisible();
  await context.setOffline(false);
});

test("an article never opened online says so offline instead of breaking", async ({ page, context }) => {
  await signIn(page);
  const seen = insertArticle();
  const unseen = insertArticle();
  await page.goto(`/read/${seen}`);
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "How compilers lower loops" })).toBeVisible();

  await context.setOffline(true);
  await page.goto(`/read/${unseen}`).catch(() => {});
  await expect(page.getByRole("heading", { name: "You're offline" })).toBeVisible();
  await expect(page.getByText(/isn't saved for offline reading/)).toBeVisible();
  await context.setOffline(false);
});
