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

A green ✓ (or red !) badge on the icon confirms success or failure.

## How it works

The popup/background scripts call your ReadPrism instance's REST API directly:
- `POST /api/v1/sources` for sources
- `POST /api/v1/creators` for creators

The token is stored in `chrome.storage.sync` and sent only to your configured
server via the `Authorization: Bearer` header.
