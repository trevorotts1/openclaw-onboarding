#!/usr/bin/env bash
# install-page-inventory-lifecycle-cron.sh — U31/B-U17: register the daily
# maintenance-window evidence-root retention sweep for the page-inventory +
# staged lifecycle tooling.
#
# WHAT THIS DOES
# ---------------
# Reads the schedule ENTRY file this repo ships
# (schedule/skill6-page-inventory-lifecycle.cron.json — the single source of
# truth both this installer and SKILL.md's doctrine text read from, so the
# two can never drift out of sync) and registers it as an `openclaw` cron,
# idempotently, by NAME. Never duplicates: if a cron with the entry's name
# already exists, this is a no-op. Never fatal: a missing `openclaw` CLI, a
# missing `python3` parser, or a registration failure is logged and exits
# non-fatally (3) so install.sh/update-skills.sh callers can continue and
# retry on the next run — mirrors
# scripts/install-github-archive-reconcile-cron.sh's fail-open discipline
# (same shape, U24/B-U10).
#
# THIS IS THE LIVE-PROOF LEG'S INSTALLER, NOT ITS PROOF. The scheduled
# command itself (tools/ghl_inventory.py --prune) is fully live-wiring-free
# and safe today (compress-only run-evidence retention, zero live
# GoHighLevel calls) — proven offline in
# tests/test_page_inventory_lifecycle_schedule.py. Actually registering this
# cron live on an operator box and confirming the first dated run is
# DEFERRED TO the operator (parallel to U22); the live PAGE ENUMERATION half
# (funnel-id discovery) is a separate, still-unproven live leg — see
# tools/ghl_inventory.py's module docstring "ONE LIVE GAP" note.
#
# CLI
# ---
#   bash scripts/install-page-inventory-lifecycle-cron.sh [evidence-base-dir]
#
# EXIT CODES
#   0  cron already present, or registered this run
#   2  the schedule entry file itself is missing/unparsable (repo defect)
#   3  `openclaw` CLI absent, or registration failed (advisory, non-fatal —
#      caller should warn; a future run backfills)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTRY_FILE="$ROOT/schedule/skill6-page-inventory-lifecycle.cron.json"

_log() { echo "[install-page-inventory-lifecycle-cron] $*"; }

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
CRON_COMMAND_TEMPLATE="$(printf '%s\n' "$ENTRY_JSON" | sed -n '4p')"

# Substitute the evidence-base dir: arg 1, else $SKILL6_EVIDENCE_BASE env,
# else the entry file's own documented default.
EVIDENCE_BASE="${1:-${SKILL6_EVIDENCE_BASE:-$HOME/clawd/skill6-fix}}"
CRON_COMMAND="${CRON_COMMAND_TEMPLATE//\$\{SKILL6_EVIDENCE_BASE\}/$EVIDENCE_BASE}"

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
    _log "OK  '$CRON_NAME' cron present but DISABLED (tombstone: deliberately disabled or auto-disabled after failures) — leaving it disabled, NOT resurrecting"
    exit 0
    ;;
  *)
    _log "FAIL could not determine a single '$CRON_NAME' job from 'openclaw cron list --all --json' (listing unreadable, or duplicate names an operator must dedupe) — NOT registering (would risk a duplicate). Non-fatal — re-run to backfill."
    exit 3
    ;;
esac

# --no-deliver: a maintenance-window sweep is an operator-internal tick, not
# a client-facing announcement — without this flag `openclaw cron add`
# defaults the new job's delivery mode to "announce", which would fan a
# routine retention pass out as a visible notification every night. Fixed
# here at the source rather than repeating the drift the two sibling
# installers (github-archive-reconcile / routing-drift-check) shipped
# without it.
if openclaw cron add --name "$CRON_NAME" --cron "$CRON_SCHEDULE" --tz "$CRON_TZ" \
     --command "$CRON_COMMAND" --no-deliver >/dev/null 2>&1 \
   && _cron_state "$CRON_NAME"; then
  # PROVE the --no-deliver above took before calling it DONE: a CLI that
  # accepts and silently ignores the flag would otherwise get a green
  # install while the fresh job announces into client chat (finding 29's
  # exact harm).
  if _cron_ensure_silent "$CRON_NAME"; then
    _log "DONE '$CRON_NAME' cron registered ($CRON_SCHEDULE $CRON_TZ)"
    exit 0
  fi
  _log "FAIL '$CRON_NAME' was registered but its delivery announces into client chat (job '${OC_CRON_JOB_ID:-?}') and the in-place repair failed — this CLI may be ignoring --no-deliver. Non-fatal — fix: openclaw cron edit ${OC_CRON_JOB_ID:-<id>} --no-deliver"
  exit 3
fi

_log "FAIL could not register '$CRON_NAME' (openclaw cron add rc!=0, or --command/--no-deliver unsupported on this CLI build). Non-fatal — re-run to backfill."
exit 3
