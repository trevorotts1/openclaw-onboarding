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
# WIRED TO A CRON BY THIS REPO since ensure-pipeline-crons.sh v14.2.0:
# `bootstrap-validate-daily`, 05:00 daily, COMMAND kind. (The old "not wired —
# nothing here schedules itself" note was left behind by that change and was
# wrong for every box rolled since.) It still runs by hand identically.
#
# HOW A FAILURE IS HEARD. The cron is SILENT by design — a maintenance job must
# never auto-announce into the box owner's chat. Silent must not mean unheard,
# so a FAILING run escalates here, in the script, on the OPERATOR path only:
# the Rescue Rangers webhook, the same channel scripts/disk-usage-alert.sh
# escalates on. No client chat is ever a destination. When no webhook is
# configured the run says so LOUDLY on stderr instead of failing quietly —
# an unescalated failure is still a visible one.
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

# ── OPERATOR ESCALATION ──────────────────────────────────────────────────────
# A failing run must reach a human. It goes to the OPERATOR (Rescue Rangers),
# never to the box owner: this is an internal maintenance defect, not client
# news. Mirrors the escalation in scripts/disk-usage-alert.sh — same webhook,
# same headers, same non-fatal posture. Escalation NEVER changes the exit code;
# the validator's verdict is the validator's alone.
if [ "$OVERALL_EXIT" -ne 0 ]; then
  _BOX="$(hostname 2>/dev/null || echo box)"
  _ESC_MSG="[bootstrap-validate] ${_BOX}: lean-bootstrap validation FAILED (exit ${OVERALL_EXIT}). Core files are over cap, a pointer dangles, or a ledgered block drifted. Run: bash ${BASH_SOURCE[0]:-bootstrap-validate-daily.sh}"
  if [ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" ]; then
    _ESC_JSON_MSG="${_ESC_MSG//\\/\\\\}"; _ESC_JSON_MSG="${_ESC_JSON_MSG//\"/\\\"}"
    if curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
         -H 'Content-Type: application/json' \
         ${RESCUE_RANGERS_WEBHOOK_SECRET:+-H X-Rescue-Secret:${RESCUE_RANGERS_WEBHOOK_SECRET}} \
         -d "{\"action\":\"escalate\",\"client\":\"${_BOX}\",\"agent\":\"bootstrap-validate-daily\",\"message\":\"${_ESC_JSON_MSG}\"}" \
         --max-time 15 >/dev/null 2>&1; then
      echo "ESCALATED to operator (rescue-rangers): ${_ESC_MSG}" >&2
    else
      # The escalation itself failed. That is the silent-failure class this
      # block exists to kill, so it is reported LOUDLY rather than swallowed.
      echo "ALERT-UNDELIVERED: bootstrap validation FAILED and the operator escalation POST did not succeed." >&2
      echo "ALERT-UNDELIVERED: ${_ESC_MSG}" >&2
    fi
  else
    # No operator route configured on this box. Refusing to invent one — a
    # client chat is never a fallback — but the failure is still made loud.
    echo "ALERT-UNDELIVERED: bootstrap validation FAILED and no operator escalation route is configured on this box." >&2
    echo "ALERT-UNDELIVERED: set RESCUE_RANGERS_WEBHOOK_URL to route this to the operator. No client chat is ever used as a fallback." >&2
    echo "ALERT-UNDELIVERED: ${_ESC_MSG}" >&2
  fi
fi

say "=== done, exit=$OVERALL_EXIT ==="
exit "$OVERALL_EXIT"
