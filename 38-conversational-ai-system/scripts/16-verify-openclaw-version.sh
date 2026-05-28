#!/usr/bin/env bash
# 16-verify-openclaw-version.sh
# Skill 38 — Step O.3 (Detect OpenClaw version and verify the schema is
# current). Halts if version < 2026.5.22 (strict-schema baseline). Runs
# `openclaw config validate` and surfaces any deprecation warnings.
set -euo pipefail

MIN_VERSION="2026.5.22"

if ! command -v openclaw >/dev/null 2>&1; then
  echo "[O.3] ERROR: 'openclaw' CLI not found on PATH. Install OpenClaw and re-run." >&2
  exit 1
fi

RAW_VERSION="$(openclaw --version 2>&1 | tr -d '\r' | head -n1 || true)"
# Extract a YYYY.M.P style version token from the line
VERSION="$(printf '%s' "$RAW_VERSION" | grep -oE '20[0-9]{2}\.[0-9]+\.[0-9]+' | head -n1 || true)"
if [ -z "$VERSION" ]; then
  echo "[O.3] ERROR: could not parse version from output: $RAW_VERSION" >&2
  exit 1
fi
echo "[O.3] Detected OpenClaw version: $VERSION"

# Numeric compare YYYY.M.P
ver_ge() {
  # $1 >= $2 ?
  printf '%s\n%s\n' "$2" "$1" | sort -t. -k1,1n -k2,2n -k3,3n -C
}

if ! ver_ge "$VERSION" "$MIN_VERSION"; then
  echo "[O.3] HALT: OpenClaw $VERSION is below the strict-schema baseline ($MIN_VERSION)." >&2
  echo "       Update OpenClaw before proceeding:" >&2
  echo "         npm install -g openclaw@latest    # Mac" >&2
  echo "         docker compose pull && docker compose up -d --force-recreate    # Hostinger VPS" >&2
  exit 1
fi

echo "[O.3] Version check passed (>= $MIN_VERSION)."

# Validate config
VALIDATE_OUT="$(openclaw config validate 2>&1 || true)"
VALIDATE_RC=0
openclaw config validate >/dev/null 2>&1 || VALIDATE_RC=$?

if [ "$VALIDATE_RC" -ne 0 ]; then
  echo "[O.3] HALT: 'openclaw config validate' failed (exit $VALIDATE_RC)." >&2
  echo "$VALIDATE_OUT" >&2
  exit 1
fi
echo "[O.3] 'openclaw config validate' returned 0."

# Detect deprecation warnings
DEPRECATIONS="$(printf '%s\n' "$VALIDATE_OUT" | grep -iE 'deprecat|mcpServers' || true)"
if [ -n "$DEPRECATIONS" ]; then
  echo "[O.3] Deprecation warnings detected:" >&2
  printf '%s\n' "$DEPRECATIONS" >&2
  echo "[O.3] Surface these to the operator — see ~/clawd/MEMORY.md note on mcpServers schema drift." >&2
fi

echo "[O.3] OK"
