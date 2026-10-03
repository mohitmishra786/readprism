/**
 * ReadPrism service worker — offline shell + stale-while-revalidate.
 *
 * Goals (kept intentionally minimal):
 * - App shell (HTML navigations) loads from cache when offline, so the digest
 *   is readable on a subway. Content data is still fetched live when online.
 * - Static assets (JS/CSS/fonts) use stale-while-revalidate for fast loads.
 *
 * Non-goals: we do NOT cache article bodies or API responses here — the in-app
 * reader fetches content live, and the ranking signals need fresh data.
 */
const CACHE_VERSION = "readprism-v1";
const APP_SHELL = ["/", "/digest", "/feed", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(APP_SHELL).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
      )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only handle GET.
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // EC-01: digest + reader content GETs are network-first with cache
  // fallback, so yesterday's digest and opened articles stay readable
  // offline. Mutations and telemetry are never touched (they are not GETs).
  const isOfflineReadableApi =
    url.pathname === "/api/v1/digest/latest" || /^\/api\/v1\/content\/[^/]+$/.test(url.pathname);
  if (isOfflineReadableApi) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            // waitUntil keeps the worker alive until the cache write lands;
            // otherwise the worker can stop with the write pending and the
            // article stays unavailable offline (CodeRabbit).
            event.waitUntil(
              caches
                .open(CACHE_VERSION)
                .then((cache) => cache.put(request, response.clone()))
                .catch(() => {})
            );
          }
          return response;
        })
        .catch(() =>
          caches.match(request).then(
            (r) =>
              r ||
              new Response(JSON.stringify({ detail: "offline and not previously loaded" }), {
                status: 503,
                headers: { "Content-Type": "application/json" },
              })
          )
        )
    );
    return;
  }

  // Navigations: network-first, fall back to cached shell when offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Only cache successful responses — caching 4xx/5xx would replay
          // transient errors as the offline fallback (cache poisoning).
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy)).catch(() => {});
          }
          return response;
        })
        .catch(() => caches.match(request).then((r) => r || caches.match("/digest")))
    );
    return;
  }

  // Same-origin static assets: stale-while-revalidate.
  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((response) => {
            // Don't poison the cache with error responses.
            if (response.ok) {
              const copy = response.clone();
              caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy)).catch(() => {});
            }
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
