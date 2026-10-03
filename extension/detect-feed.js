// Feed detection (EC-02): relay any <link rel="alternate"> feed URL to the
// background script. Content scripts cannot touch chrome.storage.session
// (trusted-contexts only, CodeRabbit), so messaging is the portable path.

(function () {
  const FEED_TYPES = [
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
    "application/json",
  ];
  const links = document.querySelectorAll('link[rel="alternate"][type][href]');
  for (const link of links) {
    const type = (link.getAttribute("type") || "").toLowerCase();
    if (FEED_TYPES.includes(type) && link.href) {
      try {
        chrome.runtime.sendMessage({ type: "feed-found", pageUrl: location.href, feedUrl: link.href });
      } catch (_e) {
        /* extension context invalidated — ignore */
      }
      return;
    }
  }
  // Also recognize being ON a feed page (served as XML).
  const root = document.documentElement && document.documentElement.nodeName;
  if (root === "rss" || root === "feed" || root === "RDF") {
    try {
      chrome.runtime.sendMessage({ type: "feed-found", pageUrl: location.href, feedUrl: location.href });
    } catch (_e) {
      /* ignore */
    }
  }
})();
