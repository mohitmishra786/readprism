# ReadPrism browser extension

A Manifest V3 browser extension for one-click addition of the current page to
ReadPrism — as a **source** (any publication/blog/feed) or as a **creator**
(Substack/YouTube/Medium/Reddit/blog).

## Install (developer mode)

1. Open `chrome://extensions` (or `edge://extensions`, `about:addons` in Firefox).
2. Enable **Developer mode**.
3. Click **Load unpacked** and select this `extension/` folder.

## Configure

1. Click the extension icon → **Set API token / server**.
2. Enter your ReadPrism server URL (default `http://localhost:8000` for self-hosted).
3. Paste your ReadPrism access token (from your account settings).

## Use

- Click the extension icon on any page → **Add page as source** / **Add page as creator**.
- Or right-click the page → **Add page as source/creator in ReadPrism**.

A green OK (or red !) badge on the icon confirms success or failure.

## How it works

The popup/background scripts call your ReadPrism instance's REST API directly:
- `POST /api/v1/sources` for sources
- `POST /api/v1/creators` for creators

The token is stored in `chrome.storage.local` (never synced) and sent only to
your configured server via the `Authorization: Bearer` header.

## Permissions

The extension does not ask for access to every site (#214):

- **Your ReadPrism server only.** When you save the server URL in the options,
  the browser asks you to allow that one origin (`optional_host_permissions`).
  `http://localhost:8000` is allowed by default for self-hosting.
- **The current tab, when you click.** Feed detection runs only when you open
  the popup, using `activeTab` + `scripting`. Nothing runs on pages you merely
  visit.
- `contextMenus` for the right-click items and `storage` for your settings.
