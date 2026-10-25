#!/usr/bin/env bash
# install-skill6-maintenance-crons.sh — the ONE Skill 6 maintenance-installer
# entry point: runs every intended installer, then reports which cron jobs are
# actually registered.
#
# WHY (finding 27): update-skills.sh discovers a skill's installer with
#   for _c in "$SKILL_DIR"/scripts/install-*.sh; do [ -x "$_c" ] && break; done
# Skill 06 ships four of them. The glob sorts, so the loop stopped at
# install-github-archive-reconcile-cron.sh and the inventory, routing-drift and
# selector-drift installers never ran on any box (live cron list: archive
# present, the other three absent). They are named explicitly below.
#
# CLI
#   bash scripts/install-skill6-maintenance-crons.sh [--idempotent] [--check-only]
#     --idempotent  accepted and ignored — every installer is already
#                   idempotent, and update-skills.sh passes this flag to every
#                   installer it runs.
#     --check-only  report registration; run no installer.
#
# No positional argument is forwarded to an installer: three of the four take
# the evidence directory as $1 and would swallow a flag as a path.
#
# EXIT CODES
#   0  every intended job is registered
#   2  a shipped schedule entry is missing/unparsable (repo defect)
#   3  a job is absent or unreadable, or an installer reported non-zero
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
SCHEDULE="$ROOT/schedule"

_log() { echo "[skill6-maintenance] $*"; }

CHECK_ONLY=0
for _arg in "$@"; do
  case "$_arg" in
    --idempotent) ;;
    --check-only) CHECK_ONLY=1 ;;
    *) _log "WARN ignoring unknown argument: $_arg" ;;
  esac
done

# ONE row per intended job: <installer>:<schedule entry>. Both files ship in
# this repo, so this list — not a glob — is the definition of "all".
JOBS="install-github-archive-reconcile-cron.sh:skill6-github-archive-reconcile-sweep.cron.json
install-page-inventory-lifecycle-cron.sh:skill6-page-inventory-lifecycle.cron.json
install-routing-drift-check-cron.sh:skill6-routing-drift-check.cron.json
install-selector-drift-probe-cron.sh:skill6-selector-drift-probe.cron.json"

_INSTALL_BAD=0
_ENTRIES=""
for _row in $JOBS; do
  _installer="${_row%%:*}"
  _entry="${_row##*:}"
  _ENTRIES="${_ENTRIES}${_entry}
"
  if [ ! -f "$SCRIPTS/$_installer" ]; then
    _log "FAIL installer missing: scripts/$_installer"
    _INSTALL_BAD=1
    continue
  fi
  [ "$CHECK_ONLY" -eq 1 ] && continue
  _rc=0
  bash "$SCRIPTS/$_installer" || _rc=$?
  if [ "$_rc" -eq 0 ]; then
    _log "installer OK: $_installer"
  else
    # Advisory by contract (3 = CLI absent or registration failed). It is
    # still surfaced so the roll withholds the .wired sentinel and retries.
    _log "installer ADVISORY rc=$_rc: $_installer (re-run backfills)"
    _INSTALL_BAD=1
  fi
done

command -v python3 >/dev/null 2>&1 || {
  _log "FAIL python3 unavailable — cannot read the shipped schedule entries"
  exit 2
}

# Job names come from the schedule entries themselves, never from this file:
# one source of truth for what each installer registers.
_JOB_NAMES="$(python3 - "$SCHEDULE" $_ENTRIES <<'PYEOF'
import json, os, sys
base = sys.argv[1]
for entry in sys.argv[2:]:
    try:
        with open(os.path.join(base, entry)) as fh:
            name = json.load(fh).get("name", "")
    except Exception:
        name = ""
    if not name:
        sys.stderr.write("unreadable schedule entry: %s\n" % entry)
        sys.exit(2)
    print(name)
PYEOF
)" || { _log "FAIL could not read the shipped schedule entries"; exit 2; }

_LIST_RAW=""
if command -v openclaw >/dev/null 2>&1; then
  # --all: the default listing hides disabled jobs, so a disabled-but-present
  # job would read as ABSENT here. Unsupported --all on an older CLI simply
  # yields an unreadable list, which is reported as UNKNOWN, never ABSENT.
  _LIST_RAW="$(openclaw cron list --all --json 2>/dev/null)" || _LIST_RAW=""
fi

# shellcheck disable=SC2086
_STATUSES="$(OC_CRON_RAW="$_LIST_RAW" python3 - $_JOB_NAMES <<'PYEOF'
import json, os, sys
input_names = sys.argv[1:]
if not input_names:
    sys.exit(2)
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
except Exception:
    sys.exit(2)
jobs = data if isinstance(data, list) else (data.get("jobs") or [])
registered = {j.get("name") for j in jobs if isinstance(j, dict)}
if not isinstance(jobs, list):
    sys.exit(2)
for name in input_names:
    print("%s\t%s" % ("REGISTERED" if name in registered else "ABSENT", name))
PYEOF
)" || _STATUSES=""

_BAD=0
if [ -n "$_STATUSES" ]; then
  _TOTAL=0
  _OK=0
  while IFS=$'\t' read -r _state _name; do
    [ -n "${_name:-}" ] || continue
    _TOTAL=$((_TOTAL + 1))
    if [ "$_state" = "REGISTERED" ]; then
      _OK=$((_OK + 1))
      _log "REGISTERED  $_name"
    else
      _BAD=1
      _log "ABSENT      $_name"
    fi
  done <<EOF
$_STATUSES
EOF
  _log "registration: $_OK/$_TOTAL intended Skill 6 maintenance jobs registered"
else
  # D10: an unreadable list is UNKNOWN, never "absent".
  _BAD=1
  for _name in $_JOB_NAMES; do
    _log "UNKNOWN     $_name (openclaw cron list unreadable)"
  done
fi

if [ "$_BAD" -eq 1 ] || [ "$_INSTALL_BAD" -eq 1 ]; then
  exit 3
fi
exit 0
