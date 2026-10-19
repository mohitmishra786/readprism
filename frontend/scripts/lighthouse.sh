#!/usr/bin/env bash
# Lighthouse scores for the landing page and the signed-in reader (#216).
# Needs the stack from playwright.stack.config.ts running (API :8000,
# frontend :3001) and an article id:   scripts/lighthouse.sh <content_id>
set -euo pipefail
cd "$(dirname "$0")/.."
ID="${1:?usage: scripts/lighthouse.sh <content_id>}"
API="${E2E_API_URL:-http://localhost:8000}"
WEB="${E2E_BASE_URL:-http://localhost:3001}"
CHROME_PATH="$(node -e "console.log(require('@playwright/test').chromium.executablePath())")"
export CHROME_PATH
jar="$(mktemp)"
email="lighthouse-$(date +%s)@example.com"
curl -sf -X POST "$API/api/v1/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"Lighthouse-123!\"}" >/dev/null
curl -sf -c "$jar" -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -H 'X-Auth-Mode: cookie' -d "{\"email\":\"$email\",\"password\":\"Lighthouse-123!\"}" >/dev/null
# httpOnly cookies are written with an "#HttpOnly_" prefix.
cookie="$(sed 's/^#HttpOnly_//' "$jar" | awk '!/^#/ && NF>=7 {printf "%s=%s; ", $6, $7}')"
mkdir -p lighthouse
for target in "landing|$WEB/" "reader|$WEB/read/$ID"; do
  name="${target%%|*}"
  npx -y lighthouse@12 "${target#*|}" --quiet --chrome-flags="--headless=new" \
    --only-categories=performance,accessibility,best-practices,seo \
    --extra-headers="{\"Cookie\":\"$cookie\"}" \
    --output=json --output-path="lighthouse/$name.json" >/dev/null 2>&1
  node -e "const r=require('./lighthouse/$name.json');console.log('$name', Object.fromEntries(Object.entries(r.categories).map(([k,v])=>[k,Math.round(v.score*100)])))"
done
