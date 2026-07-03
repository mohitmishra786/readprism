const apiBaseEl = document.getElementById("apiBase");
const tokenEl = document.getElementById("token");
const savedEl = document.getElementById("saved");

chrome.storage.sync.get({ apiBase: "http://localhost:8000", token: "" }, (cfg) => {
  apiBaseEl.value = cfg.apiBase;
  tokenEl.value = cfg.token;
});

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.sync.set(
    {
      apiBase: apiBaseEl.value.trim().replace(/\/$/, ""),
      token: tokenEl.value.trim(),
    },
    () => {
      savedEl.textContent = "Saved.";
      setTimeout(() => (savedEl.textContent = ""), 2000);
    }
  );
});
