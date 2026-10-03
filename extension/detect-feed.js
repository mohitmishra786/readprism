// Feed detection (EC-02): stash any <link rel="alternate"> feed URL for the
// popup/background to offer as the subscribe target.

(function () {
  const FEED_TYPES = ["application/rss+xml", "application/atom+xml", "application/feed+json", "application/json"];
  const links = document.querySelectorAll('link[rel="alternate"][type][href]');
  for (const link of links) {
    const type = (link.getAttribute("type") || "").toLowerCase();
    if (FEED_TYPES.includes(type) && link.href) {
      chrome.storage.session.set({ [`feed:${location.href}`]: link.href });
      return;
    }
  }
  // Also recognize being ON a feed page (served as XML).
  const root = document.documentElement && document.documentElement.nodeName;
  if (root === "rss" || root === "feed" || root === "RDF") {
    chrome.storage.session.set({ [`feed:${location.href}`]: location.href });
  }
})();
