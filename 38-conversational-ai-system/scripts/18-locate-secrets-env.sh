#!/usr/bin/env bash
# 18-locate-secrets-env.sh
# Skill 38 — Step O.5 (Locate the secrets/env file).
# Searches the canonical OpenClaw env locations. If multiple exist, asks
# the operator to disambiguate. If none, creates the default with mode 600.
# Persists the path to $HOME/.openclaw/.skill-38-secrets-env-path.
#
# MAC ENV NOTE (Step O.5): unlike a VPS (Docker), which keeps env in
# /docker/<project>/.env, a Mac install stores secrets in BOTH
# ~/clawd/secrets/.env AND ~/.openclaw/.env. Check (and add keys to) BOTH —
# never claim a key is missing without checking both. This script searches
# both Mac locations below.
set -euo pipefail

OS="$(uname -s)"
mkdir -p "$HOME/.openclaw"
STATE_FILE="$HOME/.openclaw/.skill-38-secrets-env-path"

if [ "$OS" = "Darwin" ]; then
  # Mac: env lives in BOTH ~/clawd/secrets/.env and ~/.openclaw/.env (check both).
  CANDIDATES_LIST=(
    "$HOME/clawd/secrets/.env"
    "$HOME/.openclaw/.env"
    "$HOME/.openclaw/secrets.env"
    "$HOME/.openclaw/secrets/.env"
  )
  DEFAULT_CREATE="$HOME/.openclaw/.env"
else
  CANDIDATES_LIST=(
    "/data/.openclaw/.env"
    "/data/.openclaw/secrets.env"
    "/data/.openclaw/secrets/.env"
    "$HOME/.openclaw/.env"
    "$HOME/.openclaw/secrets.env"
  )
  if [ -d "/data/.openclaw" ]; then
    DEFAULT_CREATE="/data/.openclaw/.env"
  else
    DEFAULT_CREATE="$HOME/.openclaw/.env"
  fi
fi

FOUND=()
for c in "${CANDIDATES_LIST[@]}"; do
  [ -f "$c" ] && FOUND+=("$c")
done

# Dedupe
if [ "${#FOUND[@]}" -gt 0 ]; then
  IFS=$'\n' FOUND=($(printf '%s\n' "${FOUND[@]}" | sort -u))
  unset IFS
fi

N="${#FOUND[@]}"
SECRETS_ENV_PATH=""

if [ "$N" -eq 1 ]; then
  SECRETS_ENV_PATH="${FOUND[0]}"
  echo "[O.5] Single env file detected: $SECRETS_ENV_PATH" >&2
elif [ "$N" -gt 1 ]; then
  echo "[O.5] Multiple env files found. Which one is canonical?" >&2
  i=1
  for f in "${FOUND[@]}"; do
    SIZE="$(wc -c < "$f" 2>/dev/null | tr -d ' ')"
    echo "  $i. $f  (${SIZE} bytes)" >&2
    i=$((i+1))
  done
  echo "Reply with the number:" >&2
  read -r CHOICE
  if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "$N" ]; then
    echo "Invalid selection: $CHOICE" >&2
    exit 1
  fi
  SECRETS_ENV_PATH="${FOUND[$((CHOICE-1))]}"
else
  echo "[O.5] No env file found. Creating: $DEFAULT_CREATE (mode 600)" >&2
  mkdir -p "$(dirname "$DEFAULT_CREATE")"
  touch "$DEFAULT_CREATE"
  chmod 600 "$DEFAULT_CREATE"
  SECRETS_ENV_PATH="$DEFAULT_CREATE"
fi

# Ensure mode 600 even on pre-existing files (best-effort, won't fail run)
chmod 600 "$SECRETS_ENV_PATH" 2>/dev/null || true

printf '%s\n' "$SECRETS_ENV_PATH" > "$STATE_FILE"
echo "$SECRETS_ENV_PATH"
