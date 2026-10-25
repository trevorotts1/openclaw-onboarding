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
# REGISTERED IS NOT ENABLED (2026-10-25 fix). A presence-only check is a
# false-done generator: a live box was observed with `agent-browser-reaper`
# registered and `enabled=false` (finding 28, oct-25-fixes.md). The row is
# present, so the old check printed PASS — while the hourly hard-crash
# backstop never ran. This script therefore reads the job's `enabled` state
# (falling back to the documented computed `status: "disabled"` field) out of
# the SAME listing `oc_cron_present` just used, and FAILS LOUDLY when the job
# is registered but disabled. It never enables anything: reactivation is a
# mutating registry action that requires explicit operator authorization.
# An absent `enabled`/`status` is UNKNOWN (2), never assumed-enabled — the
# whole point is that presence alone proves nothing about running.
#
# USAGE
#   scripts/check-agent-browser-reaper-schedule.sh
#
# EXIT CODES
#   0  PASS — the cron named "agent-browser-reaper" is registered AND enabled
#   1  ABSENT — `openclaw cron list` ran cleanly and found no such name
#   2  UNKNOWN — could not determine presence/enabled-state (no `openclaw`
#      CLI, neither jq nor python3 to parse `--json`, or the payload carried
#      no usable `enabled`/`status`) — never claims PASS on a failure, so a
#      broken check can never mask a disabled or absent reaper
#   3  DISABLED — registered but enabled=false; the reaper will never run.
#      Deliberately a DISTINCT non-zero code so callers can tell "the job is
#      there but switched off" from "the job was never installed"
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
  # Read enabled-state + schedule for this one name (by name only — never the
  # raw multi-job payload, which can carry OTHER jobs' message bodies). Use
  # the SAME feature-detected "show disabled jobs" flags oc_cron_present just
  # used, otherwise a disabled row can be absent from the listing and we would
  # be guessing instead of proving.
  _detected="$(oc_cron_list_json_flags 2>/dev/null || true)"
  raw=""
  if [[ -n "$_detected" ]]; then
    # shellcheck disable=SC2086  # intentional word-split: "--status all" is 2 argv tokens
    raw="$(openclaw cron list --json $_detected 2>/dev/null)" || raw=""
  else
    raw="$(openclaw cron list --json 2>/dev/null)" || raw=""
  fi

  # Prints "<enabled-flag>\t<schedule>": flag 1=enabled, 0=disabled, ?=unknown.
  parsed=""
  if [[ -n "$raw" ]] && command -v python3 >/dev/null 2>&1; then
    parsed="$(OC_CRON_RAW="$raw" python3 - "$CRON_NAME" <<'PYEOF' 2>/dev/null
import json, os, sys
name = sys.argv[1]
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError
except Exception:
    sys.exit(0)
for j in jobs:
    if not isinstance(j, dict) or j.get("name") != name:
        continue
    en = j.get("enabled")
    if isinstance(en, str):
        en = en.strip().lower() not in ("", "false", "0", "no", "disabled")
    if en is None and isinstance(j.get("status"), str):
        en = j["status"].strip().lower() != "disabled"
    flag = "1" if en is True else ("0" if en is False else "?")
    sched = j.get("cron") or j.get("schedule") or ""
    if isinstance(sched, dict):
        sched = sched.get("expr") or sched.get("cron") or ""
    print("%s\t%s" % (flag, sched))
    break
PYEOF
)"
  elif [[ -n "$raw" ]] && command -v jq >/dev/null 2>&1; then
    parsed="$(printf '%s' "$raw" | jq -r --arg n "$CRON_NAME" '
      ( if type == "array" then . elif (type == "object" and (.jobs | type) == "array") then .jobs else empty end )
      | map(select(.name == $n))
      | if length == 0 then empty else
          .[0]
          | (if has("enabled") then .enabled
             else (if (((.status // "") | ascii_downcase) == "disabled") then false else null end)
             end) as $e
          | ((.cron // .schedule // "")
              | if type == "object" then (.expr // .cron // "") else . end) as $s
          | "\(if $e == true then "1" elif $e == false then "0" else "?" end)\t\($s)"
        end' 2>/dev/null
    )"
  fi

  _enabled=""
  schedule=""
  if [[ "$parsed" == *$'\t'* ]]; then
    _enabled="${parsed%%$'\t'*}"
    schedule="${parsed#*$'\t'}"
  fi

  if [[ "$_enabled" == "1" ]]; then
    if [[ -n "$schedule" ]]; then
      _log "PASS — REGISTERED and ENABLED: '$CRON_NAME' (schedule: $schedule)"
    else
      _log "PASS — REGISTERED and ENABLED: '$CRON_NAME'"
    fi
    exit 0
  fi

  if [[ "$_enabled" == "0" ]]; then
    _log "FAIL — DISABLED: '$CRON_NAME' is registered but enabled=false, so the hourly hard-crash backstop NEVER RUNS. Presence is not proof it runs. This check never mutates the registry: reactivation requires explicit operator authorization."
    exit 3
  fi

  _log "UNKNOWN — '$CRON_NAME' is REGISTERED but its enabled-state could not be read from 'openclaw cron list --json' (no usable 'enabled'/'status' field, or no parser produced one). Presence alone is not proof it runs."
  exit 2
fi

_log "FAIL — ABSENT: no cron named '$CRON_NAME' found via 'openclaw cron list --json'. Register it: scripts/ensure-pipeline-crons.sh (idempotent, name-keyed) or install.sh/update-skills.sh's end-of-run cron wiring."
exit 1
