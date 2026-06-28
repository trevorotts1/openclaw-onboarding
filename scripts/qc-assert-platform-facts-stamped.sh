#!/usr/bin/env bash
# qc-assert-platform-facts-stamped.sh — W7.4 platform-facts QC assertion.
#
# Fails (exit 1) if the active AGENTS.md for this box:
#   (a) Does not contain the <!-- PLATFORM_FACTS_V1 --> marker, OR
#   (b) The platform recorded in the stamp does not match the detected platform.
#
# Exit codes:
#   0  — PLATFORM_FACTS_V1 stamp present and platform label is consistent
#   1  — INVARIANT VIOLATED (stamp absent or platform mismatch)
#   2  — could not resolve AGENTS.md path (warn-only in qc-system-integrity)
#
# Wired into:
#   - scripts/qc-system-integrity.sh  CHECK X.14
#   - 23-ai-workforce-blueprint/scripts/prove-zhe.py  (W1.3 ZHE acceptance prover)
#
# Run standalone:
#   bash scripts/qc-assert-platform-facts-stamped.sh
#
# v1.0.0 (W7.4)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_UTILS="$SCRIPT_DIR/../shared-utils"

# ── Detect OC_ROOT ────────────────────────────────────────────────────────────
if [ -d "/data/.openclaw" ]; then
  OC_ROOT="/data/.openclaw"
  DETECTED_PLATFORM="vps"
elif [ -d "$HOME/.openclaw" ]; then
  OC_ROOT="$HOME/.openclaw"
  DETECTED_PLATFORM="mac"
elif [ -d "$HOME/clawd" ]; then
  OC_ROOT="$HOME/clawd"
  DETECTED_PLATFORM="mac-legacy"
else
  echo "INVARIANT VIOLATED — cannot detect OpenClaw root (no /data/.openclaw or ~/.openclaw)" >&2
  exit 2
fi

# ── Resolve the active AGENTS.md path ────────────────────────────────────────
# Mirror the same resolution logic used in apply-fleet-standards.sh (Step 5a).
AGENTS_FILE=""

# Step 1: shared Python helper (PRD 1.11 — preferred when installed)
if [ -f "$SHARED_UTILS/resolve_injected_core_files.py" ]; then
  _ws=$(OC_JSON="$OC_ROOT/openclaw.json" python3 -c "
import sys, os
sys.path.insert(0, '$SHARED_UTILS')
from resolve_injected_core_files import resolve_injected_core_files
try:
    r = resolve_injected_core_files('main')
    print(r['workspace'])
except Exception:
    pass
" 2>/dev/null) || _ws=""
  [ -n "$_ws" ] && AGENTS_FILE="$_ws/AGENTS.md"
fi

# Step 2: agents.list[main].workspace from openclaw.json
if [ -z "$AGENTS_FILE" ] && [ -f "$OC_ROOT/openclaw.json" ]; then
  _ws=$(python3 -c "
import json, os, sys
try:
    cfg = json.load(open('$OC_ROOT/openclaw.json'))
    for ag in cfg.get('agents', {}).get('list', []) or []:
        if isinstance(ag, dict) and ag.get('id') == 'main':
            ws = ag.get('workspace')
            if ws:
                print(os.path.expanduser(ws)); sys.exit(0)
except Exception:
    pass
" 2>/dev/null) || _ws=""
  [ -n "$_ws" ] && AGENTS_FILE="$_ws/AGENTS.md"
fi

# Step 3: agents.defaults.workspace via CLI
if [ -z "$AGENTS_FILE" ] && command -v openclaw >/dev/null 2>&1; then
  _ws=$(openclaw config get agents.defaults.workspace 2>/dev/null | head -1 | python3 -c "
import sys, json, os
try:
    raw = sys.stdin.read().strip()
    print(os.path.expanduser(json.loads(raw) if raw.startswith('\"') else raw))
except Exception:
    pass
" 2>/dev/null) || _ws=""
  [ -n "$_ws" ] && AGENTS_FILE="$_ws/AGENTS.md"
fi

# Step 4: canonical default
if [ -z "$AGENTS_FILE" ]; then
  AGENTS_FILE="$OC_ROOT/workspace/AGENTS.md"
fi

if [ ! -f "$AGENTS_FILE" ]; then
  echo "INVARIANT VIOLATED — AGENTS.md not found at resolved path: $AGENTS_FILE" >&2
  exit 2
fi

# ── Check 1: marker present ───────────────────────────────────────────────────
PLATFORM_FACTS_MARKER="<!-- PLATFORM_FACTS_V1 -->"
if ! grep -qF "$PLATFORM_FACTS_MARKER" "$AGENTS_FILE"; then
  echo "INVARIANT VIOLATED — PLATFORM_FACTS_V1 marker absent from $AGENTS_FILE" >&2
  echo "  Remedy: run bash scripts/apply-fleet-standards.sh (W7.2)" >&2
  exit 1
fi

# ── Check 2: platform label consistency ──────────────────────────────────────
# Extract the platform value from the stamp table (| Platform | <value> |).
STAMPED_PLATFORM=$(grep -A 10 "$PLATFORM_FACTS_MARKER" "$AGENTS_FILE" \
  | grep -E '^\| Platform ' \
  | head -1 \
  | sed 's/|[^|]*|[[:space:]]*//' \
  | sed 's/[[:space:]]*|[[:space:]]*//' \
  | tr -d '|' \
  | xargs 2>/dev/null) || STAMPED_PLATFORM=""

if [ -z "$STAMPED_PLATFORM" ]; then
  echo "INVARIANT VIOLATED — PLATFORM_FACTS_V1 block found but platform label unreadable in $AGENTS_FILE" >&2
  exit 1
fi

# The stamp uses "mac", "mac-legacy", "vps-hostinger", "vps-contabo", "vps-unknown".
# We accept any stamp that STARTS WITH the detected platform prefix.
# (e.g. stamp="vps-hostinger" matches detected="vps")
if echo "$STAMPED_PLATFORM" | grep -qE "^${DETECTED_PLATFORM}"; then
  echo "PASS — PLATFORM_FACTS_V1 present in $AGENTS_FILE (platform=${STAMPED_PLATFORM}, detected=${DETECTED_PLATFORM})"
  exit 0
else
  echo "INVARIANT VIOLATED — platform mismatch in $AGENTS_FILE" >&2
  echo "  Detected platform : $DETECTED_PLATFORM" >&2
  echo "  Stamped platform  : $STAMPED_PLATFORM" >&2
  echo "  Remedy: run bash scripts/apply-fleet-standards.sh to re-stamp (W7.2)" >&2
  exit 1
fi
