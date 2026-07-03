// Popup logic: trigger add-source/add-creator and surface the result.

const statusEl = document.getElementById("status");
const sourceBtn = document.getElementById("add-source");
const creatorBtn = document.getElementById("add-creator");

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
