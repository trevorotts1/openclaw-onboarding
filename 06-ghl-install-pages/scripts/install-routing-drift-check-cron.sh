#!/usr/bin/env bash
# install-routing-drift-check-cron.sh — U23/B-U9 item: register the monthly
# maintenance-window routing-drift live proof.
#
# WHAT THIS DOES
# ---------------
# Reads the schedule ENTRY file this repo ships
# (schedule/skill6-routing-drift-check.cron.json — the single source of
# truth both this installer and the entry's own doctrine text describe)
# and registers it as an `openclaw` cron, idempotently, by NAME. Never
# duplicates: if a cron with the entry's name already exists, this is a
# no-op. Never fatal: a missing `openclaw` CLI, a missing `python3` parser,
# or a registration failure is logged and exits non-fatally (3) so
# install.sh/update-skills.sh callers can continue and retry on the next run
# — mirrors scripts/install-github-archive-reconcile-cron.sh's fail-open
# discipline (U24/B-U10), which mirrors scripts/ensure-pipeline-crons.sh's.
#
# THIS IS THE LIVE-PROOF LEG'S INSTALLER, NOT ITS PROOF. B-U9's offline
# CODE-MERGE gate only requires the schedule ENTRY file to exist and name
# the routing-drift-check tool (asserted by name, proven in
# tests/test_routing_drift_check_maintenance_schedule.py) — this installer
# is the mechanism that would register it live on an operator box; actually
# firing it and confirming the first dated receipt is DEFERRED TO U22.
#
# CLI
# ---
#   bash scripts/install-routing-drift-check-cron.sh [evidence-base-dir] [project-dir]
#
# EXIT CODES
#   0  cron already present, or registered this run
#   2  the schedule entry file itself is missing/unparsable (repo defect)
#   3  `openclaw` CLI absent, or registration failed (advisory, non-fatal —
#      caller should warn; a future run backfills)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTRY_FILE="$ROOT/schedule/skill6-routing-drift-check.cron.json"

_log() { echo "[install-routing-drift-check-cron] $*"; }

if [[ ! -f "$ENTRY_FILE" ]]; then
  _log "FAIL schedule entry file not found: $ENTRY_FILE"
  exit 2
fi

command -v python3 >/dev/null 2>&1 || { _log "FAIL python3 not available to parse the schedule entry"; exit 2; }

# Parse the entry file (name/schedule/tz/command) via python3 — no jq
# dependency for the entry file itself (it's small, fixed-shape JSON we ship).
ENTRY_JSON="$(python3 - "$ENTRY_FILE" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as fh:
    d = json.load(fh)
for k in ("name", "schedule", "tz", "command"):
    if k not in d:
        print(f"MISSING:{k}", file=sys.stderr)
        sys.exit(1)
print(d["name"])
print(d["schedule"])
print(d["tz"])
print(d["command"])
PYEOF
)" || { _log "FAIL schedule entry file is missing a required field (name/schedule/tz/command)"; exit 2; }

CRON_NAME="$(printf '%s\n' "$ENTRY_JSON" | sed -n '1p')"
CRON_SCHEDULE="$(printf '%s\n' "$ENTRY_JSON" | sed -n '2p')"
CRON_TZ="$(printf '%s\n' "$ENTRY_JSON" | sed -n '3p')"
CRON_COMMAND_TEMPLATE="$(printf '%s\n' "$ENTRY_JSON" | sed -n '4p')"

# Substitute both placeholders: evidence-base dir (arg 1, else
# $SKILL6_EVIDENCE_BASE env, else the entry file's own documented default)
# and the Vercel project-dir (arg 2, else
# $SKILL6_ROUTING_DRIFT_CHECK_PROJECT_DIR env, else the entry file's default).
EVIDENCE_BASE="${1:-${SKILL6_EVIDENCE_BASE:-$HOME/clawd/skill6-fix}}"
PROJECT_DIR="${2:-${SKILL6_ROUTING_DRIFT_CHECK_PROJECT_DIR:-$HOME/clawd/skill6-fix/routing-drift-check-project}}"

CRON_COMMAND="${CRON_COMMAND_TEMPLATE//\$\{SKILL6_EVIDENCE_BASE\}/$EVIDENCE_BASE}"
CRON_COMMAND="${CRON_COMMAND//\$\{SKILL6_ROUTING_DRIFT_CHECK_PROJECT_DIR\}/$PROJECT_DIR}"

if ! command -v openclaw >/dev/null 2>&1; then
  _log "SKIP openclaw CLI not on PATH — cannot register '$CRON_NAME'. Re-run once the CLI is installed."
  exit 3
fi

# Idempotency: exact-name match against `openclaw cron list --json`
# (jq -> python3, never text-table grep — same truncation-safety discipline
# as scripts/ensure-pipeline-crons.sh::_cron_present).
_cron_present() {
  local raw
  raw=$(openclaw cron list --json 2>/dev/null) || raw=""
  [[ -n "$raw" ]] || return 1
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$raw" | jq -e --arg n "$CRON_NAME" \
      '(if type=="array" then . else .jobs // [] end) | map(select(.name == $n)) | length > 0' \
      >/dev/null 2>&1
    return $?
  fi
  OC_CRON_RAW="$raw" python3 - "$CRON_NAME" <<'PYEOF' 2>/dev/null
import json, os, sys
name = sys.argv[1]
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
except Exception:
    sys.exit(1)
jobs = data if isinstance(data, list) else data.get("jobs", [])
sys.exit(0 if any(j.get("name") == name for j in jobs) else 1)
PYEOF
}

if _cron_present; then
  _log "OK  '$CRON_NAME' cron already present — nothing to do"
  exit 0
fi

if openclaw cron add --name "$CRON_NAME" --cron "$CRON_SCHEDULE" --tz "$CRON_TZ" \
     --command "$CRON_COMMAND" >/dev/null 2>&1 \
   && _cron_present; then
  _log "DONE '$CRON_NAME' cron registered ($CRON_SCHEDULE $CRON_TZ)"
  exit 0
fi

_log "FAIL could not register '$CRON_NAME' (openclaw cron add rc!=0, or --command unsupported on this CLI build). Non-fatal — re-run to backfill."
exit 3
