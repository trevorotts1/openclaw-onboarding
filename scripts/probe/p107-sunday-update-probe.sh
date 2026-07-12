#!/usr/bin/env bash
# p107-sunday-update-probe.sh — P1-07 (c)3: per-box Sunday-update-cron presence
# probe + Docker-VPS survives-a-container-restart check. SHIPS IN P6-01 (built
# and QC'd now; run against live fleet boxes only in the final rollout phase).
#
# WHAT THIS CLOSES
# -----------------
# P1-07's remaining verified gap: "installed ≠ armed" — setup-weekly-update.sh
# existing in the repo does not mean the Sunday 3am cron is actually present in
# a given box's crontab. `setup-weekly-update.sh`'s OWN presence check
# (`crontab -l | grep "update-restart-if-needed"`) is a truncated-text grep —
# fine for a human-run installer deciding add-or-skip, but per meta-rule 2.4
# and the v19.47.0 lesson (oc_cron_present in shared-utils/cron-lib.sh — the
# `cron list` TEXT TABLE truncation that caused the 6x-duplicate-cron
# incident), a PROBE that decides a fleet-wide pass/fail verdict must do exact
# structural matching, never a substring grep. This script:
#
#   1. Parses `crontab -l` into (schedule, command) pairs field-by-field (never
#      a whole-line substring match) and asserts EXACT equality against the
#      canonical schedule + canonical absolute script path that
#      setup-weekly-update.sh itself installs — for BOTH the Sunday 3:00 AM
#      onboarding/CC updater and the Saturday 23:59 OpenClaw CLI updater.
#   2. On a miss, with --remediate, re-runs setup-weekly-update.sh from the
#      currently-checked-out onboarding repo to install the missing cron(s) —
#      idempotent (setup-weekly-update.sh already no-ops when its own exact
#      grep finds the line, so a partial-miss re-run cannot double-install the
#      job that IS present).
#   3. Docker-VPS boxes: verifies the CC checkout lives under a path that
#      SURVIVES `docker compose up -d --force-recreate` (N40 — an update that
#      doesn't survive a container restart is a false completion). The
#      architectural answer already baked into this repo + the CC repo is that
#      VPS installs land under /data/... specifically because /data is the
#      persistent bind-mounted volume (scripts/install/vps-docker-bootstrap.sh
#      in the CC repo: ECOSYSTEM_DIR="/data/projects/command-center") — this
#      probe verifies that mount is actually in place on THIS box, not merely
#      assumed from the install path convention.
#
# GROUNDED FINDING (documented here, not asserted elsewhere): the CC Sunday
# update itself (run-full-install.sh --update-only, in-container git pull +
# npm install + pm2 restart via cc_route_update_through_canonical_path) never
# invokes `docker compose` at all — it only touches files/processes INSIDE the
# already-running container, exactly like the Mac path. There is today no
# separate docker-compose-managed "CC container" to recreate for a code-only
# update; `docker compose up -d --force-recreate` only matters for this box
# when something ELSE (an image/dependency bump to the OpenClaw container
# itself) recreates it — a DIFFERENT maintenance action from the CC Sunday
# update. This probe does not fabricate a --force-recreate step that does not
# exist in the CC-update path; it verifies the actual invariant that matters
# for CC specifically: the checkout + DB survive that outer recreation because
# they live on the persistent /data mount.
#
# USAGE
#   p107-sunday-update-probe.sh [--json] [--box <label>] [--remediate]
#
# EXIT CODES
#   0  fully armed  (both crons present, exact match; /data persistent if VPS)
#   1  degraded     (one or more checks failed) — operator/fleet-ledger attention
#   2  usage error
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

JSON=0
REMEDIATE=0
BOX="${OPENCLAW_BOX_LABEL:-$(hostname -s 2>/dev/null || echo unknown)}"

while [ $# -gt 0 ]; do
  case "$1" in
    --json) JSON=1 ;;
    --remediate) REMEDIATE=1 ;;
    --box) shift; BOX="${1:-$BOX}" ;;
    -h|--help) sed -n '2,55p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

# ---- canonical targets (must match scripts/setup-weekly-update.sh exactly) ----
SUNDAY_SCHEDULE="0 3 * * 0"
SUNDAY_CMD="$HOME/.openclaw/skills/.update-restart-if-needed"
SATURDAY_SCHEDULE="59 23 * * 6"
SATURDAY_CMD="$HOME/.openclaw/skills/.openclaw-self-update"

SUNDAY_PRESENT=0
SATURDAY_PRESENT=0
SUNDAY_LINE=""
SATURDAY_LINE=""

# _exact_cron_present <schedule 5 fields> <exact command path>
# Reads crontab -l, splits EVERY non-comment/non-blank line into its 5
# schedule fields + the remainder as the command, and requires BOTH the
# schedule tuple AND the command to match EXACTLY (after trimming). This is
# deliberately NOT `grep -q "$cmd"` — a substring match would false-positive
# on a line that merely mentions the path in a comment, and would false-NEGATIVE
# match a line whose command differs only by extra trailing args, which a raw
# grep -F would still (wrongly) call present. Exact field comparison avoids
# both failure directions.
_exact_cron_present() {
  local want_min want_hr want_dom want_mon want_dow want_cmd
  read -r want_min want_hr want_dom want_mon want_dow <<<"$1"
  want_cmd="$2"
  local line
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    case "$line" in \#*) continue ;; esac
    local f1 f2 f3 f4 f5 rest
    read -r f1 f2 f3 f4 f5 rest <<<"$line"
    if [ "$f1" = "$want_min" ] && [ "$f2" = "$want_hr" ] && [ "$f3" = "$want_dom" ] \
       && [ "$f4" = "$want_mon" ] && [ "$f5" = "$want_dow" ] && [ "$rest" = "$want_cmd" ]; then
      printf '%s' "$line"
      return 0
    fi
  done < <(crontab -l 2>/dev/null)
  return 1
}

SUNDAY_LINE="$(_exact_cron_present "$SUNDAY_SCHEDULE" "$SUNDAY_CMD")" && SUNDAY_PRESENT=1
SATURDAY_LINE="$(_exact_cron_present "$SATURDAY_SCHEDULE" "$SATURDAY_CMD")" && SATURDAY_PRESENT=1

REMEDIATED=0
if [ "$REMEDIATE" -eq 1 ] && { [ "$SUNDAY_PRESENT" -eq 0 ] || [ "$SATURDAY_PRESENT" -eq 0 ]; }; then
  SETUP_SCRIPT="$REPO_ROOT/scripts/setup-weekly-update.sh"
  if [ -f "$SETUP_SCRIPT" ]; then
    bash "$SETUP_SCRIPT" >/dev/null 2>&1
    REMEDIATED=1
    # Re-check after remediation (exact match again — never trust the
    # installer's own exit code as proof of the live crontab state).
    SUNDAY_LINE="$(_exact_cron_present "$SUNDAY_SCHEDULE" "$SUNDAY_CMD")" && SUNDAY_PRESENT=1
    SATURDAY_LINE="$(_exact_cron_present "$SATURDAY_SCHEDULE" "$SATURDAY_CMD")" && SATURDAY_PRESENT=1
  fi
fi

# ---- Docker-VPS persistent-mount check ----
IS_DOCKER=0
[ -f /.dockerenv ] && IS_DOCKER=1
if [ "$IS_DOCKER" -eq 0 ] && [ -f /proc/1/cgroup ] && grep -qE 'docker|containerd' /proc/1/cgroup 2>/dev/null; then
  IS_DOCKER=1
fi

DATA_PERSISTENT=1
DATA_PERSISTENT_CHECKED=0
CC_VPS_DIR="/data/projects/command-center"
if [ "$IS_DOCKER" -eq 1 ]; then
  DATA_PERSISTENT_CHECKED=1
  if [ -d /data ]; then
    # A genuine bind/volume mount shows up as its own line in /proc/mounts
    # with mount point exactly "/data"; a plain directory inside the
    # container's writable layer does not. This is the structural proof that
    # /data/projects/command-center (and therefore the CC checkout + DB)
    # survives `docker compose up -d --force-recreate`, which discards the
    # container's writable layer but never a bind-mounted host volume.
    if command -v mountpoint >/dev/null 2>&1; then
      mountpoint -q /data 2>/dev/null && DATA_PERSISTENT=1 || DATA_PERSISTENT=0
    elif [ -r /proc/mounts ]; then
      awk '{print $2}' /proc/mounts | grep -qx '/data' && DATA_PERSISTENT=1 || DATA_PERSISTENT=0
    else
      DATA_PERSISTENT=0 # cannot prove it — fail closed, never assume
    fi
  else
    DATA_PERSISTENT=0 # /data missing entirely on a Docker box — CC would not survive recreation
  fi
fi

OVERALL_OK=1
[ "$SUNDAY_PRESENT" -eq 1 ] || OVERALL_OK=0
[ "$SATURDAY_PRESENT" -eq 1 ] || OVERALL_OK=0
if [ "$IS_DOCKER" -eq 1 ] && [ "$DATA_PERSISTENT" -eq 0 ]; then OVERALL_OK=0; fi

CHECKED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ "$JSON" -eq 1 ]; then
  python3 - "$BOX" "$SUNDAY_PRESENT" "$SUNDAY_LINE" "$SATURDAY_PRESENT" "$SATURDAY_LINE" \
    "$IS_DOCKER" "$DATA_PERSISTENT_CHECKED" "$DATA_PERSISTENT" "$REMEDIATED" "$OVERALL_OK" "$CHECKED_AT" <<'PYEOF'
import json, sys
box, sun_p, sun_l, sat_p, sat_l, is_docker, data_checked, data_ok, remediated, overall_ok, checked_at = sys.argv[1:12]
print(json.dumps({
    "box": box,
    "checked_at": checked_at,
    "sunday_cron_present": bool(int(sun_p)),
    "sunday_cron_line": sun_l or None,
    "saturday_cron_present": bool(int(sat_p)),
    "saturday_cron_line": sat_l or None,
    "is_docker_vps": bool(int(is_docker)),
    "data_mount_checked": bool(int(data_checked)),
    "data_mount_persistent": bool(int(data_ok)) if int(data_checked) else None,
    "remediated_this_run": bool(int(remediated)),
    "overall_armed": bool(int(overall_ok)),
}, indent=2))
PYEOF
else
  echo "P1-07 Sunday-update-probe — box: $BOX  ($CHECKED_AT)"
  if [ "$SUNDAY_PRESENT" -eq 1 ]; then
    echo "  [OK]   Sunday 3:00 AM updater cron — exact match: $SUNDAY_LINE"
  else
    echo "  [MISS] Sunday 3:00 AM updater cron NOT found (exact schedule+command match failed)"
  fi
  if [ "$SATURDAY_PRESENT" -eq 1 ]; then
    echo "  [OK]   Saturday 23:59 OpenClaw-CLI-update cron — exact match: $SATURDAY_LINE"
  else
    echo "  [MISS] Saturday 23:59 OpenClaw-CLI-update cron NOT found (exact schedule+command match failed)"
  fi
  if [ "$IS_DOCKER" -eq 1 ]; then
    if [ "$DATA_PERSISTENT" -eq 1 ]; then
      echo "  [OK]   Docker VPS: /data is a persistent mount — CC checkout + DB survive 'docker compose up -d --force-recreate'"
    else
      echo "  [MISS] Docker VPS: /data is NOT a verified persistent mount — a container recreate would WIPE the CC checkout/DB (N40 false-completion risk)"
    fi
  fi
  [ "$REMEDIATED" -eq 1 ] && echo "  [INFO] --remediate ran scripts/setup-weekly-update.sh; re-checked above"
  if [ "$OVERALL_OK" -eq 1 ]; then
    echo "  VERDICT: ARMED"
  else
    echo "  VERDICT: DEGRADED — see MISS lines above; re-run with --remediate to install missing crons"
  fi
fi

[ "$OVERALL_OK" -eq 1 ] && exit 0 || exit 1
