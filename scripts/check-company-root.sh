#!/usr/bin/env bash
# check-company-root.sh — PRD 1.9 HEARTBEAT check for the canonical company root.
#
# Verifies that:
#   1. The master_files directory exists and is locally materialized (not iCloud-offloaded).
#   2. The company_root (master_files/zero-human-company/) exists and has at least
#      one company subdirectory.
#
# Exit codes:
#   0 = all clear
#   1 = company root missing or iCloud-offloaded (alerts operator via Telegram if configured)
#
# Usage (called from HEARTBEAT.md cron or install.sh preflight):
#   bash check-company-root.sh
#   OPENCLAW_COMPANY_SLUG=blackceo bash check-company-root.sh
#
# Environment:
#   MASTER_FILES_DIR   — override the master_files root (PRD 1.9)
#   OPENCLAW_COMPANY_SLUG — target a specific company slug
#   TELEGRAM_OPERATOR_CHAT_ID — if set, send an alert on failure
#   OPENCLAW_GATEWAY_TOKEN    — required for openclaw message send

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB="$REPO_ROOT/lib-shared.sh"
[ -f "$LIB" ] && source "$LIB"

# ── helpers ────────────────────────────────────────────────────────────────────
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }

# ── resolve master_files via get_openclaw_paths() ─────────────────────────────
PYTHON="$(command -v python3 || command -v python || echo "")"
if [ -z "$PYTHON" ]; then
  red "ERROR: python3 not found — cannot resolve paths."
  exit 1
fi

MASTER_FILES=""
COMPANY_ROOT=""
PLATFORM=""

eval "$($PYTHON 2>/dev/null - <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath("$SCRIPT_DIR")), "shared-utils"))
try:
    from detect_platform import get_openclaw_paths
    p = get_openclaw_paths()
    print(f"MASTER_FILES={p['master_files']}")
    print(f"COMPANY_ROOT={p['company_root']}")
    print(f"PLATFORM={p['platform']}")
except Exception as e:
    print(f"# detect_platform error: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
)" || true

# Fallback if Python eval fails
if [ -z "$MASTER_FILES" ]; then
  if [ -n "${MASTER_FILES_DIR:-}" ]; then
    MASTER_FILES="$MASTER_FILES_DIR"
  elif [ -d /data/.openclaw ]; then
    MASTER_FILES="/data/openclaw-master-files"
  else
    MASTER_FILES="$HOME/Downloads/openclaw-master-files"
  fi
  COMPANY_ROOT="$MASTER_FILES/zero-human-company"
fi

# ── check 1: master_files exists ──────────────────────────────────────────────
if [ ! -d "$MASTER_FILES" ]; then
  MSG="[HEARTBEAT] FAIL — master_files directory not found: $MASTER_FILES"
  red "$MSG"
  _alert_operator "$MSG"
  exit 1
fi

# ── check 2: iCloud offload detection (Mac only) ─────────────────────────────
# iCloud-offloaded placeholder files show as 0-byte stubs.
# The .nosync trick and /usr/bin/brctl show/update are Mac-specific.
if [ "$(uname)" = "Darwin" ]; then
  OFFLOADED_COUNT=0
  if command -v find >/dev/null 2>&1; then
    # Offloaded iCloud files are 0-byte and have the com.apple.icloud.desktop xattr
    # OR their name ends in .icloud (the evicted placeholder form).
    OFFLOADED_COUNT=$(find "$MASTER_FILES" -name "*.icloud" 2>/dev/null | wc -l | tr -d ' ')
  fi
  if [ "$OFFLOADED_COUNT" -gt 0 ]; then
    MSG="[HEARTBEAT] WARN — $OFFLOADED_COUNT iCloud-offloaded file(s) detected under $MASTER_FILES. Run: brctl download \"$MASTER_FILES\" OR right-click > Download Now in Finder."
    yellow "$MSG"
    _alert_operator "$MSG"
    # Non-fatal warning — offloaded files may still be readable via on-demand download
  fi
fi

# ── check 3: company_root exists and has at least one company ─────────────────
if [ ! -d "$COMPANY_ROOT" ]; then
  MSG="[HEARTBEAT] WARN — company_root not yet created: $COMPANY_ROOT (no workforce built yet — OK on fresh install)"
  yellow "$MSG"
  exit 0
fi

COMPANY_COUNT=$(find "$COMPANY_ROOT" -mindepth 1 -maxdepth 1 -type d ! -name '.*' 2>/dev/null | wc -l | tr -d ' ')
if [ "$COMPANY_COUNT" -eq 0 ]; then
  yellow "[HEARTBEAT] INFO — company_root exists but no company built yet: $COMPANY_ROOT"
  exit 0
fi

# ── check 4: target slug exists (if provided) ─────────────────────────────────
if [ -n "${OPENCLAW_COMPANY_SLUG:-}" ]; then
  SLUG_DIR="$COMPANY_ROOT/$OPENCLAW_COMPANY_SLUG"
  if [ ! -d "$SLUG_DIR" ]; then
    MSG="[HEARTBEAT] FAIL — Company slug '$OPENCLAW_COMPANY_SLUG' not found at $SLUG_DIR"
    red "$MSG"
    _alert_operator "$MSG"
    exit 1
  fi
  green "[HEARTBEAT] PASS — Company '$OPENCLAW_COMPANY_SLUG' present at $SLUG_DIR"
else
  green "[HEARTBEAT] PASS — $COMPANY_COUNT company/companies found under $COMPANY_ROOT"
fi

exit 0

# ── internal: send Telegram alert if configured ───────────────────────────────
_alert_operator() {
  local msg="$1"
  local chat_id="${TELEGRAM_OPERATOR_CHAT_ID:-${RESCUE_RANGERS_HELP_CHAT_ID:-}}"
  if [ -z "$chat_id" ]; then
    return 0
  fi
  if command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram -t "$chat_id" \
      -m "$msg" 2>/dev/null || true
  fi
}
