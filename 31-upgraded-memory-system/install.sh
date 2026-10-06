#!/usr/bin/env bash
# 31-upgraded-memory-system/install.sh — schedule the two nightly memory
# maintenance jobs on this box. Runs from install.sh (fresh install) and from
# update-skills.sh's per-skill wiring loop (every roll), on Mac and inside the
# Docker container alike: both jobs are `openclaw cron --command` jobs, which the
# gateway runs as a plain shell command — no agent turn, no tokens, --no-deliver.
#
#   memory-cache-prune  (40 2 * * *)  scripts/memory-cache-prune.sh
#       deletes dead embedding-cache rows + compacts; see that script's header.
#   memory-index-check  (0 2 * * *)   scripts/memory-index-check.sh
#       READ-ONLY drift report. Never reindexes, never re-embeds: repairing a
#       drifted index calls the paid embedding provider, so it stays an
#       operator decision.
#
# Idempotent by exact cron NAME (shared-utils/cron-lib.sh oc_cron_present), and
# a durable tombstone (oc_cron_tombstoned) is honored: an operator who removed a
# job keeps it removed. Commands point at this skill's installed directory, so a
# roll that updates the scripts updates what the cron runs.
#
# Exit: 0 both jobs present, 3 openclaw CLI missing or a registration failed
# (update-skills.sh withholds the .wired sentinel and retries next roll).
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
CRON_LIB="$HERE/../shared-utils/cron-lib.sh"
TAG="[skill31-maintenance]"

command -v openclaw >/dev/null 2>&1 || { echo "$TAG SKIP openclaw CLI not on PATH; re-run later"; exit 3; }
[ -f "$CRON_LIB" ] || { echo "$TAG FAIL $CRON_LIB not found"; exit 3; }
# shellcheck source=../shared-utils/cron-lib.sh
. "$CRON_LIB"

rc=0
ensure_cron() { # ensure_cron <name> <schedule> <script>
  local name="$1" expr="$2" cmd="bash $HERE/scripts/$3"
  if oc_cron_tombstoned "$name"; then
    echo "$TAG SKIP $name is tombstoned on this box"
  elif oc_cron_present "$name"; then
    echo "$TAG OK   $name already scheduled"
  elif openclaw cron add --name "$name" --cron "$expr" --no-deliver --command "$cmd" >/dev/null 2>&1 \
       && oc_cron_present "$name"; then
    echo "$TAG DONE $name scheduled ($expr)"
  else
    echo "$TAG FAIL could not schedule $name. Manual: openclaw cron add --name $name --cron '$expr' --no-deliver --command '$cmd'"
    rc=3
  fi
}

ensure_cron memory-index-check "0 2 * * *" memory-index-check.sh
ensure_cron memory-cache-prune "40 2 * * *" memory-cache-prune.sh
exit $rc
