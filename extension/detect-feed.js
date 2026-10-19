// Feed detection (EC-02, #214). Injected on demand into the active tab with
// chrome.scripting.executeScript when the user opens the popup (activeTab
// grants that one tab), instead of a content script on every page. Returns
// the feed URL or null.

// eslint-disable-next-line no-unused-vars
function detectFeedInPage() {
  const FEED_TYPES = [
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
    "application/json",
  ];
  const links = document.querySelectorAll('link[rel="alternate"][type][href]');
  for (const link of links) {
    const type = (link.getAttribute("type") || "").toLowerCase();
    if (FEED_TYPES.includes(type) && link.href) return link.href;
  }
  // Being ON a feed page (served as XML) counts too.
  const root = document.documentElement && document.documentElement.nodeName;
  if (root === "rss" || root === "feed" || root === "RDF") return location.href;
  return null;
}

detectFeedInPage();
