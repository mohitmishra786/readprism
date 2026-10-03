// Popup logic: trigger add-source/add-creator and surface the result.

const statusEl = document.getElementById("status");
const sourceBtn = document.getElementById("add-source");
const creatorBtn = document.getElementById("add-creator");

// On open, surface the result of a context-menu-triggered add (if any), so the
// user sees feedback even if they opened the popup after the badge appeared.
chrome.storage.session.get(["lastResult", "lastUrl"], ({ lastResult, lastUrl }) => {
  if (lastResult) {
    showResult(lastResult);
    // Clear so it doesn't persist across unrelated popup opens.
    chrome.storage.session.remove(["lastResult", "lastUrl"]);
  }
});

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function showResult(result) {
  if (result.ok) {
    const name =
      result.data?.name || result.data?.creator?.display_name || "Added";
    statusEl.textContent = `✓ ${name}`;
    statusEl.className = "ok";
  } else {
    statusEl.textContent = `✗ ${result.error || "Failed"}`;
    statusEl.className = "err";
  }
}

sourceBtn.addEventListener("click", async () => {
  statusEl.textContent = "Adding…";
  statusEl.className = "";
  const tab = await getActiveTab();
  chrome.runtime.sendMessage({ type: "add-source", tab }, showResult);
});

creatorBtn.addEventListener("click", async () => {
  statusEl.textContent = "Adding…";
  statusEl.className = "";
  const tab = await getActiveTab();
  chrome.runtime.sendMessage({ type: "add-creator", tab }, showResult);
});

document.getElementById("options").addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

// --- Save & rate + detected feed (EC-02) ---

function ask(type, extra = {}) {
  return new Promise((resolve) => chrome.runtime.sendMessage({ type, ...extra }, resolve));
}

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function saveRate(rating) {
  statusEl.textContent = rating ? "Saving & rating…" : "Saving…";
  statusEl.className = "";
  const tab = await currentTab();
  const result = await ask("save-rate", { tab, rating });
  showResult(
    result.ok
      ? { ok: true, data: { name: rating === 1 ? "Saved 👍" : rating === -1 ? "Saved 👎" : "Saved" } }
      : result
  );
}

document.getElementById("save-good").addEventListener("click", () => saveRate(1));
document.getElementById("save-bad").addEventListener("click", () => saveRate(-1));

// If the content script detected a feed for this page, offer subscribing to
// the FEED (not the HTML page).
(async () => {
  const tab = await currentTab();
  if (!tab?.url) return;
  ask("detect-feed", { tab }).then((feedUrl) => {
    if (!feedUrl) return;
    const btn = document.getElementById("add-feed");
    btn.hidden = false;
    btn.textContent = "Subscribe to detected feed";
    btn.title = feedUrl;
    btn.addEventListener("click", () => {
      statusEl.textContent = "Adding feed…";
      statusEl.className = "";
      const feedTab = { ...tab, url: feedUrl };
      chrome.runtime.sendMessage({ type: "add-source", tab: feedTab }, showResult);
    });
  });
})();
