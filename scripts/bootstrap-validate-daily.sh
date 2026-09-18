#!/usr/bin/env bash
# bootstrap-validate-daily.sh — lean-bootstrap health check for ONE box.
#
# Runs validate-core-references.py against every workspace on this box, prints
# the JSON result for each, prints the live byte size of each bootstrap file,
# reads the real per-file and total caps from openclaw.json (never hardcoded),
# flags anything over cap, and exits non-zero if any workspace failed validation
# or any cap was exceeded.
#
# WHY IT EXISTS. Bootstrap files are re-billed to the model on EVERY turn, and
# every fleet roll stamps managed blocks into them. Without a standing check,
# growth is invisible until a box is paying for tens of thousands of characters
# of reference text on every single turn. This replaces a per-box OpenClaw cron
# that was erroring on every run (a rejected model override) with a zero-token
# host-level script.
#
# NOT WIRED TO A CRON BY THIS REPO — deliberately. It ships so an operator can
# run it by hand or schedule it per box. Nothing here schedules itself.
#
# PLATFORM. Paths follow the same convention every installer in this repo uses:
#   VPS  (/data/.openclaw/openclaw.json exists) -> /data/.openclaw, /data/clawd
#   Mac  (default)                              -> $HOME/.openclaw, $HOME/clawd
# Override any of it with OC_ROOT / OC_CONFIG / OC_WORKSPACES / VALIDATOR.
#
# Usage: bootstrap-validate-daily.sh [--quiet] [extra args passed to the validator]

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

QUIET=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --quiet) QUIET=1 ;;
    *) ARGS+=("$a") ;;
  esac
done

# ── Platform resolution ──────────────────────────────────────────────────────
if [ -z "${OC_ROOT:-}" ]; then
  if [ -f /data/.openclaw/openclaw.json ]; then OC_ROOT="/data/.openclaw"
  else OC_ROOT="$HOME/.openclaw"; fi
fi
CONFIG="${OC_CONFIG:-$OC_ROOT/openclaw.json}"
VALIDATOR="${VALIDATOR:-$SCRIPT_DIR/validate-core-references.py}"

if [ -z "${OC_WORKSPACES:-}" ]; then
  if [ "$OC_ROOT" = "/data/.openclaw" ]; then
    OC_WORKSPACES="/data/clawd:$OC_ROOT/workspace"
  else
    OC_WORKSPACES="$HOME/clawd:$OC_ROOT/workspace"
  fi
fi

FILES=(AGENTS.md USER.md SOUL.md IDENTITY.md TOOLS.md MEMORY.md)

say() { [ "$QUIET" -eq 1 ] || echo "$@"; }

say "=== bootstrap-validate-daily.sh :: $(date '+%Y-%m-%d %H:%M:%S %Z') ==="

if [ ! -f "$VALIDATOR" ]; then
  echo "FATAL: validator not found at $VALIDATOR" >&2
  exit 2
fi
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 not on PATH" >&2; exit 2; }

# ── Live limits, read from config. Never hardcoded. ──────────────────────────
_read_cap() {
  CONFIG="$CONFIG" KEY="$1" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    d = json.load(open(os.environ["CONFIG"]))
    v = d.get("agents", {}).get("defaults", {}).get(os.environ["KEY"])
    print(v if isinstance(v, int) else "")
except Exception:
    print("")
PYEOF
}
PER_FILE_LIMIT="$(_read_cap bootstrapMaxChars)"
TOTAL_LIMIT="$(_read_cap bootstrapTotalMaxChars)"

say "Config: $CONFIG"
say "Live limits: bootstrapMaxChars=${PER_FILE_LIMIT:-UNSET} bootstrapTotalMaxChars=${TOTAL_LIMIT:-UNSET}"
say ""

OVERALL_EXIT=0
CHECKED_ANY=0

IFS=':' read -r -a _WS <<<"$OC_WORKSPACES"
for WS in "${_WS[@]}"; do
  [ -n "$WS" ] || continue
  if [ ! -d "$WS" ]; then
    say "--- workspace: $WS --- (absent on this box, skipped)"
    continue
  fi
  CHECKED_ANY=1
  say "--- workspace: $WS ---"

  RESULT="$(python3 "$VALIDATOR" --workspace "$WS" --from-config "$CONFIG" "${ARGS[@]}" 2>&1)"
  VALIDATOR_EXIT=$?
  say "$RESULT"

  if [ "$VALIDATOR_EXIT" -eq 0 ]; then
    say "SUMMARY [$WS]: OK"
  else
    ERR_COUNT="$(printf '%s' "$RESULT" | python3 -c '
import json,sys
try: print(len(json.load(sys.stdin).get("errors", [])))
except Exception: print("unknown")
' 2>/dev/null || echo unknown)"
    echo "SUMMARY [$WS]: FAIL: ${ERR_COUNT} errors"
    OVERALL_EXIT=1
  fi

  say ""
  say "Live byte sizes [$WS]:"
  WS_TOTAL=0
  for F in "${FILES[@]}"; do
    FPATH="$WS/$F"
    if [ -f "$FPATH" ]; then
      SIZE="$(wc -c < "$FPATH" | tr -d ' ')"
      WS_TOTAL=$((WS_TOTAL + SIZE))
      FLAG=""
      if [ -n "$PER_FILE_LIMIT" ] && [ "$SIZE" -gt "$PER_FILE_LIMIT" ]; then
        FLAG=" <== OVER per-file limit ($PER_FILE_LIMIT)"
        OVERALL_EXIT=1
      fi
      say "  $F: ${SIZE} bytes${FLAG}"
    else
      say "  $F: MISSING"
    fi
  done
  say "  TOTAL (${#FILES[@]} files): ${WS_TOTAL} bytes"
  if [ -n "$TOTAL_LIMIT" ] && [ "$WS_TOTAL" -gt "$TOTAL_LIMIT" ]; then
    echo "  <== OVER total limit ($TOTAL_LIMIT) in $WS"
    OVERALL_EXIT=1
  fi
  say ""
done

# Checking nothing is not a pass. Say so and fail, rather than report success
# for a run that never looked at a single file.
if [ "$CHECKED_ANY" -eq 0 ]; then
  echo "FAIL: no workspace found to check (looked in: $OC_WORKSPACES)" >&2
  exit 2
fi

say "=== done, exit=$OVERALL_EXIT ==="
exit "$OVERALL_EXIT"
