#!/usr/bin/env bash
# 17-backup-openclaw-config.sh
# Skill 38 — Step O.4 (Execute Backup Protocol before any config edit).
# Creates timestamped backups of openclaw.json and the env file. Idempotent:
# if a backup younger than 5 minutes already exists, skip.
set -euo pipefail

OS="$(uname -s)"
TS="$(date +%Y%m%d-%H%M%S)"

if [ "$OS" = "Darwin" ]; then
  OPENCLAW_DIR="$HOME/.openclaw"
else
  if [ -d "/data/.openclaw" ]; then
    OPENCLAW_DIR="/data/.openclaw"
  else
    OPENCLAW_DIR="$HOME/.openclaw"
  fi
fi

CONFIG_FILE="$OPENCLAW_DIR/openclaw.json"
ENV_HINT_FILE="$HOME/.openclaw/.skill-38-secrets-env-path"

backup_one() {
  local src="$1"
  local label="$2"
  if [ ! -f "$src" ]; then
    echo "[O.4] $label not found at $src — skipping."
    return 0
  fi
  # Check for recent backup (<5min)
  local recent
  recent="$(find "$(dirname "$src")" -maxdepth 1 -type f \
    -name "$(basename "$src").bak-pre-skill38-install-*" \
    -mmin -5 2>/dev/null | head -n1 || true)"
  if [ -n "$recent" ]; then
    echo "[O.4] Recent $label backup exists (<5min): $recent — skipping new backup."
    echo "$recent"
    return 0
  fi
  local dest="${src}.bak-pre-skill38-install-${TS}"
  cp "$src" "$dest"
  echo "[O.4] Backed up $label: $dest"
  echo "$dest"
}

echo "[O.4] OpenClaw dir: $OPENCLAW_DIR"
backup_one "$CONFIG_FILE" "openclaw.json"

# Env file backup (resolve via skill-38 hint file if present)
ENV_FILE=""
if [ -f "$ENV_HINT_FILE" ]; then
  ENV_FILE="$(cat "$ENV_HINT_FILE" 2>/dev/null || true)"
fi
if [ -z "$ENV_FILE" ] || [ ! -f "$ENV_FILE" ]; then
  for candidate in "$OPENCLAW_DIR/.env" "$OPENCLAW_DIR/secrets.env" "$OPENCLAW_DIR/secrets/.env"; do
    if [ -f "$candidate" ]; then ENV_FILE="$candidate"; break; fi
  done
fi
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
  backup_one "$ENV_FILE" "env file"
else
  echo "[O.4] No env file found yet — run 18-locate-secrets-env.sh first if you expected one."
fi

echo "[O.4] OK"
