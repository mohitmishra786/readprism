/**
 * Weirling service worker — offline shell + stale-while-revalidate.
 *
 * Goals (kept intentionally minimal):
 * - App shell (HTML navigations) loads from cache when offline, so the digest
 *   is readable on a subway. Content data is still fetched live when online.
 * - Static assets (JS/CSS/fonts) use stale-while-revalidate for fast loads.
 *
 * Non-goals: we do NOT cache article bodies or API responses here — the in-app
 * reader fetches content live, and the ranking signals need fresh data.
 */
const CACHE_VERSION = "readprism-v2";
const OFFLINE_ARTICLE_HTML =
  '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">' +
  '<title>Offline</title><body style="font-family:system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem">' +
  "<h1>You're offline</h1><p>This article isn't saved for offline reading. Articles you " +
  'opened while online stay readable. <a href="/digest">Back to your digest</a></p></body>';
const OFFLINE_PAGE_HTML =
  '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">' +
  '<title>Offline</title><body style="font-family:system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem;background:#0a0a0a;color:#f5f5f4">' +
  "<h1>Can't reach Weirling</h1><p>You're offline or the server isn't responding. " +
  '<a style="color:#f59e0b" href="">Try again</a></p></body>';
const APP_SHELL = ["/", "/digest", "/feed", "/manifest.json"];

// respondWith(undefined) is a hard browser error ("Returned response is
// null" in Safari), so every path must end in a real Response (#159).
function offlinePage() {
  return new Response(OFFLINE_PAGE_HTML, {
    status: 503,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

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
            // Clone now, before the page reads the body: cloning inside the
            // async callback below threw "body already used" (swallowed by
            // the catch), so API responses were never cached and offline
            // reading never worked (#216). waitUntil keeps the worker alive
            // until the cache write lands (CodeRabbit).
            const copy = response.clone();
            event.waitUntil(
              caches
                .open(CACHE_VERSION)
                .then((cache) => cache.put(request, copy))
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
        .catch(() =>
          caches.match(request).then((r) => {
            if (r) return r;
            // An article never opened online: say so plainly rather than
            // render the cached digest at an article URL (#216).
            if (url.pathname.startsWith("/read/")) {
              return new Response(OFFLINE_ARTICLE_HTML, {
                status: 503,
                headers: { "Content-Type": "text/html; charset=utf-8" },
              });
            }
            return caches.match("/digest").then((shell) => shell || offlinePage());
          })
        )
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
          .catch(() => cached || Response.error());
        return cached || network;
      })
    );
  }
});

// Opt-in digest alerts (#266): show the notification the server pushed, and
// open (or focus) the digest when it is tapped.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_e) {
    data = {};
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Weirling", {
      body: data.body || "Your digest is ready.",
      icon: "/icon.svg",
      badge: "/icon.svg",
      tag: data.tag || "readprism",
      data: { url: data.url || "/digest" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || "/digest", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if (w.url.startsWith(self.location.origin) && "focus" in w) {
          w.navigate(target);
          return w.focus();
        }
      }
      return self.clients.openWindow(target);
    })
  );
});
