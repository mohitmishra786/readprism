#!/usr/bin/env bash
# Package the ReadPrism extension for Chrome + Firefox (EC-02).
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(python3 -c "import json;print(json.load(open('manifest.json'))['version'])")
OUT="dist/readprism-extension-${VERSION}.zip"
mkdir -p dist
rm -f "$OUT"
zip -q "$OUT" manifest.json background.js popup.html popup.js options.html options.js detect-feed.js icon.svg README.md
echo "packaged: $OUT"
unzip -l "$OUT"
