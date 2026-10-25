#!/usr/bin/env bash
# lib-cron-presence.sh — shared idempotency + silent-delivery helpers for the
# Skill 6 maintenance-window cron installers (sourced, never executed).
#
# WHY THIS EXISTS (finding 30)
# ---------------------------
# `openclaw cron list --json` HIDES DISABLED JOBS (`--all` defaults to false).
# Measured on the operator box, 2026-10-25: `cron list --json` returns 17 jobs,
# `cron list --all --json` returns 55 (38 disabled). A presence check built on
# the default listing cannot see a job an operator DELIBERATELY disabled, so a
# reinstall either stacks a duplicate or resurrects the disabled schedule
# ENABLED. Every Skill 6 installer therefore queries `cron list --all --json`
# and treats a present-but-disabled job as a TOMBSTONE: report it, change
# nothing, never re-enable. Re-arming is an operator decision, not an
# installer's.
#
# WHY THE DELIVERY CHECK (finding 29)
# -----------------------------------
# A maintenance-window tick is an operator-internal sweep, not a client-facing
# announcement. `openclaw cron add` defaults a new job's delivery mode to
# "announce"; without `--no-deliver` the sweep fans out into client chat. New
# jobs get the flag at the call site; jobs that already exist are VALIDATED
# here and repaired in place with `openclaw cron edit <id> --no-deliver`
# (a flag that exists on both `cron add` and `cron edit` in the live CLI).
#
# CONTRACT — `_cron_state NAME` exit codes
# ----------------------------------------
#   0  present and ENABLED   -> OC_CRON_JOB_ID, OC_CRON_DELIVERY_MODE set
#   3  present but DISABLED  -> OC_CRON_JOB_ID set (deliberate tombstone)
#   1  absent                -> neither set
#   2  UNKNOWN               -> list failed or unparsable; NEVER treat as absent
#
# Callers run under `set -u`; every global read here is defaulted.

# _cron_state NAME — see CONTRACT above. Sets OC_CRON_JOB_ID and
# OC_CRON_DELIVERY_MODE (delivery.mode, or "none" when absent/no delivery).
_cron_state() {
  local name="${1:-}" raw out rc
  OC_CRON_JOB_ID=""
  OC_CRON_DELIVERY_MODE=""
  [[ -n "$name" ]] || return 2
  # --all is the whole point: the default listing hides disabled jobs.
  raw="$(openclaw cron list --all --json 2>/dev/null)" || return 2
  [[ -n "$raw" ]] || return 2
  out="$(OC_CRON_ALL_JSON="$raw" python3 - "$name" <<'PYEOF'
import json, os, sys
name = sys.argv[1]
try:
    data = json.loads(os.environ.get("OC_CRON_ALL_JSON", ""))
except Exception:
    sys.exit(2)
if isinstance(data, list):
    jobs = data
elif isinstance(data, dict):
    jobs = data.get("jobs")
else:
    jobs = None
if not isinstance(jobs, list):
    sys.exit(2)
for job in jobs:
    if not isinstance(job, dict) or job.get("name") != name:
        continue
    print(job.get("id") or job.get("jobId") or "")
    delivery = job.get("delivery")
    mode = delivery.get("mode") if isinstance(delivery, dict) else None
    print(mode or "none")
    disabled = job.get("enabled") is False or job.get("disabled") is True
    sys.exit(3 if disabled else 0)
sys.exit(1)
PYEOF
)"; rc=$?
  if [[ "$rc" -eq 0 || "$rc" -eq 3 ]]; then
    OC_CRON_JOB_ID="$(printf '%s\n' "$out" | sed -n '1p')"
    OC_CRON_DELIVERY_MODE="$(printf '%s\n' "$out" | sed -n '2p')"
    [[ -n "$OC_CRON_DELIVERY_MODE" ]] || OC_CRON_DELIVERY_MODE="none"
  fi
  return "$rc"
}

# _cron_delivery_silent — 0 when the job found by _cron_state cannot announce
# into chat ("none" or no delivery configured), 1 when it would announce.
_cron_delivery_silent() {
  case "${OC_CRON_DELIVERY_MODE:-none}" in
    ""|none) return 0 ;;
    *) return 1 ;;
  esac
}

# _cron_ensure_silent NAME — for an already-present, ENABLED job: 0 when its
# delivery is already silent or was repaired in place with
# `cron edit <id> --no-deliver`; 1 when drift remains (caller reports,
# non-fatal). Never enables or disables anything.
_cron_ensure_silent() {
  local name="${1:-}"
  _cron_delivery_silent && return 0
  [[ -n "${OC_CRON_JOB_ID:-}" ]] || return 1
  openclaw cron edit "$OC_CRON_JOB_ID" --no-deliver >/dev/null 2>&1 || return 1
  _cron_state "$name" || return 1
  _cron_delivery_silent
}
