#!/usr/bin/env bash
# tombstone-cron.sh — make a cron disable/removal DURABLE against
# re-registration by the fleet's own pipeline-cron registrars.
#
# WHY THIS EXISTS (fix/industry-gate-and-idempotent-crons, live-VPS finding,
# 2026-07-11):
#   On a live box, `openclaw cron list --json` was observed returning ONLY
#   ENABLED jobs (16 of 31 rows actually present) — a DISABLED cron is
#   invisible to every registrar's presence check (_cron_present /
#   oc_cron_present), so the NEXT install.sh/update-skills.sh run silently
#   RESURRECTS it. "Disable" alone is therefore not a durable kill: a fleet
#   cleanup that disables duplicate crons can be undone by the very next
#   version update.
#
#   This script writes a durable, file-based TOMBSTONE marker
#   (shared-utils/cron-lib.sh::oc_cron_tombstone/oc_cron_tombstoned) that
#   EVERY registrar wired to check it (scripts/ensure-pipeline-crons.sh,
#   39-real-estate-playbook/scripts/07-register-crons.sh,
#   38-conversational-ai-system/scripts/04-register-crons.sh) respects BEFORE
#   attempting to (re)register a cron by name — regardless of whether that
#   cron is visible in `cron list --json` at all. It mirrors the already-proven
#   BOX_PARK_MARKER pattern this repo uses for workforce-build-resume
#   (scripts/unpark-build.sh is the un-park equivalent of this script's
#   --remove mode).
#
# WHAT IT DOES NOT DO:
#   - It does NOT call `openclaw cron rm`/`cron edit` itself — actually
#     disabling/removing the LIVE cron on the gateway is a separate,
#     operator-approved action (the fleet cleanup already running). This
#     script only makes that action's effect DURABLE against this repo's own
#     registrars. Run it alongside (before or after) the actual disable/removal.
#   - It does NOT auto-discover/dedupe existing duplicate crons on a box.
#     Point it at each name you have already disabled/removed.
#
# USAGE:
#   bash scripts/tombstone-cron.sh <cron-name> [reason...]
#       Write a durable tombstone for <cron-name>. Idempotent — re-running
#       just refreshes the reason/timestamp.
#   bash scripts/tombstone-cron.sh --remove <cron-name>
#       Un-tombstone <cron-name> (operator-only — the registrar may register
#       it again on its next run).
#   bash scripts/tombstone-cron.sh --list
#       List every currently-tombstoned name on this box.
#   bash scripts/tombstone-cron.sh --status <cron-name>
#       Show whether <cron-name> is tombstoned, change nothing.

set -u

TOMBSTONE_CRON_VERSION="v1.0.0"

# ---- platform detection (VPS /data first, then Mac $HOME) — mirrors every
#      other pipeline script so paths resolve identically on both. ----
if [ -d /data/.openclaw ]; then
  OC_ROOT=/data/.openclaw
elif [ -d "${HOME:-}/.openclaw" ]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[tombstone-cron] no OpenClaw root found (.openclaw absent) — nothing to tombstone" >&2
  exit 0
fi

TOMBSTONE_DIR="$OC_ROOT/workspace/.cron-tombstones"

# Source the shared helper for the canonical write/read/remove logic (so this
# script and every registrar agree on the exact same marker path/format).
_CRON_LIB=""
for _cand in \
  "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)/../shared-utils/cron-lib.sh" \
  "$OC_ROOT/skills/shared-utils/cron-lib.sh"; do
  [ -n "$_cand" ] && [ -f "$_cand" ] && _CRON_LIB="$_cand" && break
done
if [ -n "$_CRON_LIB" ]; then
  # shellcheck source=/dev/null
  . "$_CRON_LIB"
else
  echo "[tombstone-cron] FATAL: shared-utils/cron-lib.sh not found — cannot write a tombstone in the canonical format." >&2
  exit 1
fi

usage() {
  grep '^#' "$0" | sed 's/^# \{0,1\}//'
}

case "${1:-}" in
  -h|--help)
    usage; exit 0 ;;
  --list)
    mkdir -p "$TOMBSTONE_DIR" 2>/dev/null || true
    echo "── tombstoned crons on $(hostname 2>/dev/null || echo box) ──"
    if [ -d "$TOMBSTONE_DIR" ] && [ -n "$(ls -A "$TOMBSTONE_DIR" 2>/dev/null)" ]; then
      for f in "$TOMBSTONE_DIR"/*; do
        [ -f "$f" ] || continue
        echo "  $(basename "$f"):"
        sed 's/^/    /' "$f"
      done
    else
      echo "  (none)"
    fi
    exit 0 ;;
  --status)
    NAME="${2:-}"
    if [ -z "$NAME" ]; then
      echo "[tombstone-cron] --status requires a cron name" >&2; exit 64
    fi
    if oc_cron_tombstoned "$NAME"; then
      echo "TOMBSTONED: $NAME"
      cat "$(oc_cron_tombstone_path "$NAME")" 2>/dev/null | sed 's/^/  /'
    else
      echo "not tombstoned: $NAME"
    fi
    exit 0 ;;
  --remove)
    NAME="${2:-}"
    if [ -z "$NAME" ]; then
      echo "[tombstone-cron] --remove requires a cron name" >&2; exit 64
    fi
    oc_cron_untombstone "$NAME"
    echo "[tombstone-cron] un-tombstoned '$NAME' — a registrar MAY register it again on its next run."
    exit 0 ;;
  "" )
    echo "[tombstone-cron] a cron name is required. Usage: bash scripts/tombstone-cron.sh <cron-name> [reason...]" >&2
    exit 64 ;;
  --*)
    echo "[tombstone-cron] unknown flag '${1}'. Use --list | --status <name> | --remove <name> | --help" >&2
    exit 64 ;;
esac

NAME="$1"; shift || true
REASON="$*"
[ -z "$REASON" ] && REASON="operator tombstone (no reason given) via tombstone-cron.sh $TOMBSTONE_CRON_VERSION"

if oc_cron_tombstone "$NAME" "$REASON"; then
  echo "[tombstone-cron] TOMBSTONED '$NAME' on $(hostname 2>/dev/null || echo box) — $(oc_cron_tombstone_path "$NAME")"
  echo "[tombstone-cron] every registrar wired to check oc_cron_tombstoned() will now skip '$NAME' on every future install/update run, regardless of whether it is visible in 'openclaw cron list --json'."
  echo "[tombstone-cron] this does NOT disable/remove the live cron itself — do that separately (openclaw cron rm/edit)."
  echo "[tombstone-cron] to reverse: bash scripts/tombstone-cron.sh --remove '$NAME'"
  exit 0
else
  echo "[tombstone-cron] FAILED to write tombstone for '$NAME' (could not resolve/create $TOMBSTONE_DIR)" >&2
  exit 1
fi
