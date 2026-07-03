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

document.getElementById("save").addEventListener("click", () => {
  const apiBase = apiBaseEl.value.trim().replace(/\/$/, "");
  const token = tokenEl.value.trim();
  // Persist apiBase (non-secret) to sync; token (secret) to local only.
  chrome.storage.sync.set({ apiBase }, () => {
    chrome.storage.local.set({ token }, () => {
      savedEl.textContent = "Saved.";
      setTimeout(() => (savedEl.textContent = ""), 2000);
    });
  });
});
