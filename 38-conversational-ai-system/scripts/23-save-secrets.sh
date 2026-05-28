#!/usr/bin/env bash
# 23-save-secrets.sh
# Skill 38 — Step 5: append the 5 named secrets to $SECRETS_ENV_FILE
# Idempotent: detects the v5.14 marker block and skips if already present.
# Never duplicates or clobbers existing entries.
# OS-aware via uname -s. bash -n clean.

set -euo pipefail

OS_NAME="$(uname -s)"

: "${SECRETS_ENV_FILE:?SECRETS_ENV_FILE must be set (path to env file holding playbook secrets)}"
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN must be set}"
: "${CLOUDFLARE_TUNNEL_TOKEN:?CLOUDFLARE_TUNNEL_TOKEN must be set}"
: "${HOOKS_TOKEN:?HOOKS_TOKEN must be set}"
: "${CLOUDFLARE_TUNNEL_ID:?CLOUDFLARE_TUNNEL_ID must be set}"
: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID must be set}"

mkdir -p "$(dirname "$SECRETS_ENV_FILE")"
if [ ! -f "$SECRETS_ENV_FILE" ]; then
  : > "$SECRETS_ENV_FILE"
  chmod 600 "$SECRETS_ENV_FILE" 2>/dev/null || true
fi

MARKER_BEGIN="# === Saved by OpenClaw GHL Webhook Playbook v5.14"
MARKER_END="# === End playbook v5.14 block ==="

if grep -Fq "$MARKER_BEGIN" "$SECRETS_ENV_FILE" 2>/dev/null; then
  echo "[23-save-secrets] v5.14 block already present in $SECRETS_ENV_FILE — skipping (idempotent)."
  exit 0
fi

NOW_HUMAN="$(date '+%Y-%m-%d %H:%M:%S %Z')"

{
  printf '\n%s on %s ===\n' "$MARKER_BEGIN" "$NOW_HUMAN"
  printf 'CLOUDFLARE_API_TOKEN=%s\n' "$CLOUDFLARE_API_TOKEN"
  printf 'CLOUDFLARE_TUNNEL_TOKEN=%s\n' "$CLOUDFLARE_TUNNEL_TOKEN"
  printf 'HOOKS_TOKEN=%s\n' "$HOOKS_TOKEN"
  printf 'CLOUDFLARE_TUNNEL_ID=%s\n' "$CLOUDFLARE_TUNNEL_ID"
  printf 'CLOUDFLARE_ACCOUNT_ID=%s\n' "$CLOUDFLARE_ACCOUNT_ID"
  printf '%s\n' "$MARKER_END"
} >> "$SECRETS_ENV_FILE"

case "$OS_NAME" in
  Darwin|Linux) chmod 600 "$SECRETS_ENV_FILE" 2>/dev/null || true ;;
  *) : ;;
esac

echo "[23-save-secrets] appended v5.14 block to $SECRETS_ENV_FILE"
echo "[23-save-secrets] last 15 lines:"
tail -n 15 "$SECRETS_ENV_FILE"
