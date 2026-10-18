#!/usr/bin/env bash
# Create .env (from .env.example) with freshly generated secrets.
#
#   ./scripts/init_env.sh            # writes ./.env
#   ./scripts/init_env.sh path/.env  # writes elsewhere
#
# Idempotent: existing non-placeholder values are never overwritten, so it is
# safe to re-run after upgrades that add new variables to .env.example.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE="$ROOT/.env.example"
TARGET="${1:-$ROOT/.env}"
PLACEHOLDER="change_me_to_a_long_random_string"

if [[ ! -f "$EXAMPLE" ]]; then
  echo "init_env: $EXAMPLE not found" >&2
  exit 1
fi
if [[ ! -f "$TARGET" ]]; then
  cp "$EXAMPLE" "$TARGET"
  echo "init_env: created $TARGET from .env.example"
fi
chmod 600 "$TARGET"

random_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c "import secrets; print(secrets.token_hex(32))"
  fi
}

# Set KEY to a random value when it is missing, empty or the placeholder.
ensure_secret() {
  local key="$1" current
  current="$(grep -E "^${key}=" "$TARGET" | tail -n1 | cut -d= -f2- || true)"
  if [[ -n "$current" && "$current" != "$PLACEHOLDER" ]]; then
    return
  fi
  local value
  value="$(random_hex)"
  if grep -qE "^${key}=" "$TARGET"; then
    # Portable in-place edit (BSD and GNU sed differ on -i).
    local tmp
    tmp="$(mktemp)"
    awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k{$0=k"="v} {print}' "$TARGET" > "$tmp"
    cat "$tmp" > "$TARGET"
    rm -f "$tmp"
  else
    printf '%s=%s\n' "$key" "$value" >> "$TARGET"
  fi
  echo "init_env: generated $key"
}

ensure_secret SECRET_KEY
ensure_secret REFRESH_SECRET_KEY
ensure_secret METRICS_TOKEN

echo "init_env: $TARGET is ready (APP_ENV=$(grep -E '^APP_ENV=' "$TARGET" | cut -d= -f2-))"
