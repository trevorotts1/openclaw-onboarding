#!/usr/bin/env bash
# check-agent-browser-reaper-schedule.sh — U28 (B-U14) item 4: schedule-
# PRESENCE check for the agent-browser-reaper cron.
#
# WHY THIS EXISTS
# ----------------
# B-U14's own spec text: "assert the reaper schedule is actually installed
# ... a reaper that exists but never runs is the false-done pattern." The
# reaper script (scripts/agent-browser-reaper.sh) has existed and been
# provably correct since 2026-06-23 — that alone proves nothing about whether
# it is actually SCHEDULED to run on a given box. This script is the presence
# CHECK ONLY (never registers, never mutates) — the registration itself is
# scripts/ensure-pipeline-crons.sh::_ensure_health_cron("agent-browser-reaper",
# "13 * * * *", "agent-browser-reaper.sh"), wired at the end of every
# install.sh / update-skills.sh run.
#
# CROSS-PLATFORM BY DESIGN: unlike a native launchd-plist check (Mac-only) or
# a native crontab check (meaningless inside a VPS Docker container that has
# no system cron), this repo's OWN schedule registrar
# (shared-utils/cron-lib.sh::oc_cron_present, the same exact-name, JSON,
# never-text-table-grep primitive scripts/ensure-pipeline-crons.sh's
# `_cron_present` already uses) queries `openclaw cron list --json` — the ONE
# scheduling abstraction that is uniform on Mac (backed by launchd under the
# hood) and VPS (backed by the in-container process supervisor). One script,
# run identically on either platform.
#
# BY NAME ONLY: this prints presence/absence and the registered schedule
# expression for the name "agent-browser-reaper" — never the raw `cron list
# --json` payload (which can carry other jobs' --message/--command bodies).
#
# USAGE
#   scripts/check-agent-browser-reaper-schedule.sh
#
# EXIT CODES
#   0  PRESENT — the cron named "agent-browser-reaper" is registered
#   1  ABSENT — `openclaw cron list` ran cleanly and found no such name
#   2  UNKNOWN — could not determine presence (no `openclaw` CLI, or neither
#      jq nor python3 available to parse `--json`) — never claims PRESENT on
#      a failure, so a broken check can never mask a real absence
set -u

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_REPO_ROOT="$(cd "$_HERE/../.." && pwd)"
_CRON_LIB="$_REPO_ROOT/shared-utils/cron-lib.sh"
CRON_NAME="agent-browser-reaper"

_log() { echo "[check-agent-browser-reaper-schedule] $*"; }

if ! command -v openclaw >/dev/null 2>&1; then
  _log "UNKNOWN — 'openclaw' CLI not on PATH; cannot query cron presence for '$CRON_NAME'."
  exit 2
fi

if [[ ! -f "$_CRON_LIB" ]]; then
  _log "UNKNOWN — shared-utils/cron-lib.sh not found at $_CRON_LIB (repo layout defect?)."
  exit 2
fi
# shellcheck source=/dev/null
source "$_CRON_LIB"

if ! command -v jq >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  _log "UNKNOWN — neither jq nor python3 available to parse 'openclaw cron list --json'."
  exit 2
fi

if oc_cron_present "$CRON_NAME"; then
  # Echo just the schedule expression for this one name (by name only — never
  # the raw multi-job payload, which can carry OTHER jobs' message bodies).
  schedule=""
  raw="$(openclaw cron list --json 2>/dev/null)" || raw=""
  if [[ -n "$raw" ]] && command -v python3 >/dev/null 2>&1; then
    schedule="$(OC_CRON_RAW="$raw" python3 - "$CRON_NAME" <<'PYEOF' 2>/dev/null
import json, os, sys
name = sys.argv[1]
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
except Exception:
    sys.exit(0)
jobs = data if isinstance(data, list) else data.get("jobs", [])
for j in jobs:
    if j.get("name") == name:
        sched = j.get("cron") or j.get("schedule") or ""
        if isinstance(sched, dict):
            sched = sched.get("expr") or sched.get("cron") or ""
        print(sched)
        break
PYEOF
)"
  fi
  if [[ -n "$schedule" ]]; then
    _log "PASS — PRESENT: '$CRON_NAME' is registered (schedule: $schedule)"
  else
    _log "PASS — PRESENT: '$CRON_NAME' is registered"
  fi
  exit 0
fi

_log "FAIL — ABSENT: no cron named '$CRON_NAME' found via 'openclaw cron list --json'. Register it: scripts/ensure-pipeline-crons.sh (idempotent, name-keyed) or install.sh/update-skills.sh's end-of-run cron wiring."
exit 1
