const apiBaseEl = document.getElementById("apiBase");
const tokenEl = document.getElementById("token");
const savedEl = document.getElementById("saved");

// Use chrome.storage.local for the token (a secret) — storage.sync replicates
// to the browser vendor's cloud and across all signed-in devices, widening the
// blast radius if any synced device is compromised. apiBase is non-secret, so
// it can stay in sync for convenience.
chrome.storage.local.get({ token: "" }, (local) => {
  tokenEl.value = local.token;
});
chrome.storage.sync.get({ apiBase: "http://localhost:8000" }, (cfg) => {
  apiBaseEl.value = cfg.apiBase;
});

// The extension may talk only to your own Weirling server (#214): saving
// asks the browser for access to that one origin, nothing broader.
function originPattern(apiBase) {
  try {
    const url = new URL(apiBase);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    return `${url.origin}/*`;
  } catch (_e) {
    return null;
  }
}

document.getElementById("save").addEventListener("click", async () => {
  const apiBase = apiBaseEl.value.trim().replace(/\/$/, "");
  const token = tokenEl.value.trim();
  const pattern = originPattern(apiBase);
  if (!pattern) {
    savedEl.textContent = "Enter the full server URL, e.g. https://weirling.example.com";
    return;
  }
  // Must run inside the click (user gesture) for the browser to prompt.
  const granted = await chrome.permissions.request({ origins: [pattern] }).catch(() => false);
  if (!granted) {
    savedEl.textContent = "Weirling needs access to your server to save pages. Not saved.";
    return;
  }
  // Persist apiBase (non-secret) to sync; token (secret) to local only.
  chrome.storage.sync.set({ apiBase }, () => {
    chrome.storage.local.set({ token }, () => {
      savedEl.textContent = "Saved.";
      setTimeout(() => (savedEl.textContent = ""), 2000);
    });
  });
});
