// ReadPrism extension background service worker.
// Adds context-menu items for one-click source/creator addition.

const API_BASE_DEFAULT = "http://localhost:8000";

async function getApiBase() {
  const { apiBase } = await chrome.storage.sync.get({ apiBase: API_BASE_DEFAULT });
  return apiBase.replace(/\/$/, "");
}

async function getToken() {
  // Token is a secret — read from local storage only (not sync).
  const { token } = await chrome.storage.local.get({ token: "" });
  return token;
}

async function addAsSource(tab) {
  const apiBase = await getApiBase();
  const token = await getToken();
  if (!token) {
    return { ok: false, error: "No API token set. Open extension options to add your ReadPrism token." };
  }
  const res = await fetch(`${apiBase}/api/v1/sources`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ url: tab.url }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return { ok: false, error: body.detail || `HTTP ${res.status}` };
  }
  return { ok: true, data: await res.json() };
}

async function addAsCreator(tab) {
  const apiBase = await getApiBase();
  const token = await getToken();
  if (!token) {
    return { ok: false, error: "No API token set. Open extension options to add your ReadPrism token." };
  }
  const res = await fetch(`${apiBase}/api/v1/creators`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ name_or_url: tab.url }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return { ok: false, error: body.detail || `HTTP ${res.status}` };
  }
  return { ok: true, data: await res.json() };
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "readprism-add-source",
    title: "Add page as source in ReadPrism",
    contexts: ["page"],
  });
  chrome.contextMenus.create({
    id: "readprism-add-creator",
    title: "Add page as creator in ReadPrism",
    contexts: ["page"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  let result;
  if (info.menuItemId === "readprism-add-source") {
    result = await addAsSource(tab);
  } else if (info.menuItemId === "readprism-add-creator") {
    result = await addAsCreator(tab);
  } else {
    return;
  }
  // Surface the result via a notification badge on the action icon.
  await chrome.action.setBadgeText({
    tabId: tab.id,
    text: result.ok ? "✓" : "!",
  });
  await chrome.action.setBadgeBackgroundColor({
    tabId: tab.id,
    color: result.ok ? "#16a34a" : "#dc2626",
  });
  // The popup reads the last result from storage so it can show feedback.
  await chrome.storage.session.set({ lastResult: result, lastUrl: tab.url });
});

// Expose for the popup to call directly (one-click without context menu).
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "add-source") {
    addAsSource(msg.tab).then(sendResponse);
    return true; // keep the channel open for the async response
  }
  if (msg?.type === "add-creator") {
    addAsCreator(msg.tab).then(sendResponse);
    return true;
  }
  return false;
});
