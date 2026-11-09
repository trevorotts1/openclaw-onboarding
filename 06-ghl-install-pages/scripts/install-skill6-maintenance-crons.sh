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
#   2  a shipped schedule entry is missing/unparsable (repo defect) —
#      including when a sub-installer reports one (rc 2): a re-run can never
#      backfill a repo defect, so it is never masked as advisory rc 3
#   3  a job is absent/unreadable, or an installer reported an advisory
#      non-zero (CLI absent, registration failed — re-run backfills)
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
_INSTALL_REPO_DEFECT=0
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
  case "$_rc" in
    0)
      _log "installer OK: $_installer"
      ;;
    2)
      # rc 2 is every sibling installer's "shipped schedule entry
      # missing/unparsable (repo defect)" code. A re-run can never backfill
      # it, so propagate 2 — never mask it as advisory rc 3 ("re-run
      # backfills"), which would promise a retry that can never succeed.
      _log "installer REPO DEFECT rc=2: $_installer (shipped schedule entry unusable — re-run cannot fix this)"
      _INSTALL_REPO_DEFECT=1
      ;;
    *)
      # Advisory by contract (3 = CLI absent or registration failed). It is
      # still surfaced so the roll withholds the .wired sentinel and retries.
      _log "installer ADVISORY rc=$_rc: $_installer (re-run backfills)"
      _INSTALL_BAD=1
      ;;
  esac
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
_FULL_VIS=0
_UNKNOWN_REASON="openclaw cron list unreadable"
if command -v openclaw >/dev/null 2>&1; then
  # Full visibility is FEATURE-DETECTED, never assumed — mirrors
  # shared-utils/cron-lib.sh::oc_cron_list_json_flags. `cron list` documents
  # only --agent/--json: a build that does not advertise a status flag hides
  # disabled jobs, and passing an unadvertised --all does NOT make it show
  # them (flag-ignoring builds return a readable but PARTIAL list — not the
  # unreadable one the old comment here assumed). So on such a build a missing
  # name is UNKNOWN, never ABSENT (D10): "genuinely absent" and
  # "present-but-disabled" are indistinguishable in that list.
  _HELP="$(openclaw cron list --help 2>&1 || true)"
  _LIST_ARGS="$(OC_CRON_HELP="$_HELP" python3 - <<'PYEOF'
import os, re, sys
help_text = os.environ.get("OC_CRON_HELP", "")
for cand in ("--all", "--include-disabled", "--show-disabled", "--status"):
    if re.search(r"(^|\s)" + re.escape(cand) + r"(\s|=|<|$)", help_text):
        sys.stdout.write("--status all" if cand == "--status" else cand)
        break
PYEOF
)"
  # shellcheck disable=SC2086
  _LIST_RAW="$(openclaw cron list $_LIST_ARGS --json 2>/dev/null)" || _LIST_RAW=""
  if [ -n "$_LIST_ARGS" ]; then
    _FULL_VIS=1
  else
    _UNKNOWN_REASON="this CLI advertises no full-visibility cron list flag — a disabled job cannot be told apart from an absent one"
  fi
fi

# shellcheck disable=SC2086
_STATUSES="$(OC_CRON_RAW="$_LIST_RAW" OC_FULL_VIS="$_FULL_VIS" python3 - $_JOB_NAMES <<'PYEOF'
import json, os, sys
input_names = sys.argv[1:]
if not input_names:
    sys.exit(2)
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
    jobs = data if isinstance(data, list) else (data.get("jobs") or [])
    if not isinstance(jobs, list) or any(not isinstance(j, dict) for j in jobs):
        raise ValueError("unexpected cron list shape")
except Exception:
    sys.exit(2)
full_vis = os.environ.get("OC_FULL_VIS") == "1"
registered = {j.get("name") for j in jobs}
for name in input_names:
    if name in registered:
        state = "REGISTERED"
    else:
        state = "ABSENT" if full_vis else "UNKNOWN"
    print("%s\t%s" % (state, name))
PYEOF
)" || _STATUSES=""

_BAD=0
if [ -n "$_STATUSES" ]; then
  _TOTAL=0
  _OK=0
  while IFS=$'\t' read -r _state _name; do
    [ -n "${_name:-}" ] || continue
    _TOTAL=$((_TOTAL + 1))
    case "$_state" in
      REGISTERED)
        _OK=$((_OK + 1))
        _log "REGISTERED  $_name"
        ;;
      ABSENT)
        _BAD=1
        _log "ABSENT      $_name"
        ;;
      *)
        _BAD=1
        _log "UNKNOWN     $_name ($_UNKNOWN_REASON)"
        ;;
    esac
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

if [ "$_INSTALL_REPO_DEFECT" -eq 1 ]; then
  exit 2
fi
if [ "$_BAD" -eq 1 ] || [ "$_INSTALL_BAD" -eq 1 ]; then
  exit 3
fi
exit 0
