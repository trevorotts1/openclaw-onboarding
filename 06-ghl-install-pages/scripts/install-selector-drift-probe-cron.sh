#!/usr/bin/env bash
# install-selector-drift-probe-cron.sh — U30/B-U16 item 4: register the daily
# maintenance-window selector-drift probe.
#
# WHAT THIS DOES
# ---------------
# Reads the schedule ENTRY file this repo ships
# (schedule/skill6-selector-drift-probe.cron.json — the single source of
# truth both this installer and the entry's own doctrine text describe) and
# registers it as an `openclaw` cron, idempotently, by NAME. Never
# duplicates: if a cron with the entry's name already exists, this is a
# no-op. Never fatal: a missing `openclaw` CLI, a missing `python3` parser,
# or a registration failure is logged and exits non-fatally (3) so
# install.sh/update-skills.sh callers can continue and retry on the next run
# — mirrors scripts/install-github-archive-reconcile-cron.sh (U24/B-U10) and
# scripts/install-routing-drift-check-cron.sh (U23/B-U9)'s fail-open
# discipline, whose pattern this installer mirrors.
#
# THIS IS THE LIVE-PROOF LEG'S INSTALLER, NOT ITS PROOF. B-U16 item 4's
# offline CODE-MERGE gate only requires the schedule ENTRY file to exist and
# name the selector-drift-probe script (asserted by name, proven in
# tests/test_selector_drift_probe_maintenance_schedule.py) — this installer
# is the mechanism that would register it live on an operator box; actually
# firing it daily and confirming the first dated log/board card is an
# operator-run live step.
#
# CLI
# ---
#   bash scripts/install-selector-drift-probe-cron.sh
#
# EXIT CODES
#   0  cron already present, or registered this run
#   2  the schedule entry file itself is missing/unparsable (repo defect)
#   3  `openclaw` CLI absent, or registration failed (advisory, non-fatal —
#      caller should warn; a future run backfills)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTRY_FILE="$ROOT/schedule/skill6-selector-drift-probe.cron.json"

_log() { echo "[install-selector-drift-probe-cron] $*"; }

if [[ ! -f "$ENTRY_FILE" ]]; then
  _log "FAIL schedule entry file not found: $ENTRY_FILE"
  exit 2
fi

# Shared idempotency + silent-delivery helpers (full-visibility presence
# check, disabled-job tombstones, delivery validation). Sourced after the
# entry-file check so a tampered/relocated tree still reports its own defect.
CRON_LIB="$ROOT/scripts/lib-cron-presence.sh"
[[ -f "$CRON_LIB" ]] || { _log "FAIL shared cron helper missing: $CRON_LIB (repo defect)"; exit 2; }
# shellcheck source=./lib-cron-presence.sh
source "$CRON_LIB"

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
CRON_COMMAND="$(printf '%s\n' "$ENTRY_JSON" | sed -n '4p')"

if ! command -v openclaw >/dev/null 2>&1; then
  _log "SKIP openclaw CLI not on PATH — cannot register '$CRON_NAME'. Re-run once the CLI is installed."
  exit 3
fi

# Idempotency: exact-name match against `openclaw cron list --all --json`
# (full visibility — the default listing hides deliberately disabled jobs;
# see lib-cron-presence.sh). A disabled match is a TOMBSTONE: never
# resurrected. An enabled match gets its delivery mode validated.
_cron_state "$CRON_NAME"; _cp_rc=$?
case "$_cp_rc" in
  0)
    if _cron_ensure_silent "$CRON_NAME"; then
      _log "OK  '$CRON_NAME' cron already present (delivery silent) — nothing to do"
      exit 0
    fi
    _log "FAIL '$CRON_NAME' cron already present but its delivery announces into client chat (job '${OC_CRON_JOB_ID:-?}') and the in-place repair failed. Non-fatal — fix: openclaw cron edit ${OC_CRON_JOB_ID:-<id>} --no-deliver"
    exit 3
    ;;
  1)
    : # absent — fall through and register
    ;;
  3)
    _log "OK  '$CRON_NAME' cron present but DISABLED (deliberate tombstone) — leaving it disabled, NOT resurrecting"
    exit 0
    ;;
  *)
    _log "FAIL could not read 'openclaw cron list --all --json' — presence of '$CRON_NAME' unknown, NOT registering (would risk a duplicate). Non-fatal — re-run to backfill."
    exit 3
    ;;
esac

# --no-deliver: a daily maintenance-window probe is an operator-internal tick,
# not a client-facing announcement — without this flag `openclaw cron add`
# defaults the new job's delivery mode to "announce" and the probe fans out
# into client chat. The archive and inventory installers already pass it
# (finding 29).
if openclaw cron add --name "$CRON_NAME" --cron "$CRON_SCHEDULE" --tz "$CRON_TZ" \
     --command "$CRON_COMMAND" --no-deliver >/dev/null 2>&1 \
   && _cron_state "$CRON_NAME"; then
  _log "DONE '$CRON_NAME' cron registered ($CRON_SCHEDULE $CRON_TZ)"
  exit 0
fi

_log "FAIL could not register '$CRON_NAME' (openclaw cron add rc!=0, or --command/--no-deliver unsupported on this CLI build). Non-fatal — re-run to backfill."
exit 3
