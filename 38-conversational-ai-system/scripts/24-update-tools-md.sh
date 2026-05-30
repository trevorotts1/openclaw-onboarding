#!/usr/bin/env bash
# 24-update-tools-md.sh — Skill 38: preload the CLIENT TOOLS.md with the concise,
# verified GHL Convert-and-Flow API quick-reference so the agent has the exact
# request shapes in its CORE context and replies FAST (no digging through the
# dense full reference at runtime).
#
# WHERE: the client's workspace TOOLS.md (NOT AGENTS.md). AGENTS.md = WHAT-TO-DO
# (rules/behavior); TOOLS.md = WHERE-THINGS-LIVE (tools, endpoints, API reference).
# API request shapes belong in TOOLS.md.
#
# WHAT: appends the canonical block from
#   references/ghl-api-quick-reference.md
# wrapped in the SKILL38: GHL_API_QUICK_REFERENCE marker (the same marker the
# reference file ships with), so this is a single source of truth.
#
# Idempotent: skips if the marker is already present. Backs up before any write.
# Never overwrites operator content — append-only.
#
# CONCISE by design: the block is the cheat sheet only (canonical shapes), not
# the whole API — the full per-module detail stays in
# 29-ghl-convert-and-flow/references/{conversations,calendars,payments}.md.
#
# OS-aware (matches 06-append-memory-rules.sh):
#   Darwin → $HOME/clawd/TOOLS.md
#   Linux  → /data/clawd/TOOLS.md
# Override with $TOOLS_MD or $OPENCLAW_WORKSPACE.
#
# Optional: $PUBLIC_HOSTNAME is emitted ONLY as a comment line (the client's hook
# host, for orientation) — NEVER a token, never client/personal data.

set -euo pipefail

MARKER="SKILL38: GHL_API_QUICK_REFERENCE"

# --- Resolve the skill root (this script lives at <root>/scripts/24-...) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL38_ROOT="${SKILL38_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
REF_FILE="$SKILL38_ROOT/references/ghl-api-quick-reference.md"

if [ ! -f "$REF_FILE" ]; then
  echo "[24-update-tools-md] reference block not found: $REF_FILE" >&2
  echo "[24-update-tools-md] cannot inject the GHL quick-reference — aborting." >&2
  exit 1
fi

# --- Resolve the CLIENT TOOLS.md (OS-aware, matches 06-append-memory-rules.sh) ---
case "$(uname -s)" in
  Darwin) WS_DEFAULT="$HOME/clawd" ;;
  Linux)  WS_DEFAULT="/data/clawd" ;;
  *)      WS_DEFAULT="$HOME/clawd" ;;
esac
WS="${OPENCLAW_WORKSPACE:-$WS_DEFAULT}"
TOOLS_MD="${TOOLS_MD:-$WS/TOOLS.md}"

# Create the file if the workspace exists but TOOLS.md doesn't yet (fresh install).
if [ ! -f "$TOOLS_MD" ]; then
  if [ -d "$(dirname "$TOOLS_MD")" ]; then
    printf '# TOOLS.md\n\nWhere things live: connected tools, endpoints, and API references.\n' > "$TOOLS_MD"
    echo "[24-update-tools-md] created $TOOLS_MD"
  else
    echo "[24-update-tools-md] workspace dir $(dirname "$TOOLS_MD") not found — skipping (set \$TOOLS_MD or \$OPENCLAW_WORKSPACE)" >&2
    exit 0
  fi
fi

# --- Idempotency: skip if the block is already there ---
if grep -qF "$MARKER" "$TOOLS_MD"; then
  echo "[24-update-tools-md] GHL quick-reference already present in $TOOLS_MD — preserved"
  exit 0
fi

# --- Backup before any write ---
cp -p "$TOOLS_MD" "$TOOLS_MD.bak-skill38-$(date -u +%Y%m%dT%H%M%SZ)"

# --- Append the canonical block (verbatim from the reference file) ---
{
  printf '\n'
  # PUBLIC_HOSTNAME is emitted ONLY as an orientation comment — never a token.
  if [ -n "${PUBLIC_HOSTNAME:-}" ]; then
    printf '<!-- GHL quick-reference installed by Skill 38; this client hook host: %s -->\n' "$PUBLIC_HOSTNAME"
  fi
  cat "$REF_FILE"
} >> "$TOOLS_MD"

echo "[24-update-tools-md] GHL Convert-and-Flow API quick-reference appended to $TOOLS_MD"
