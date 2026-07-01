#!/usr/bin/env bash
# wire.sh -- Skill 41 Build With AI Playbook Generator
#
# Idempotent, FAIL-SOFT post-update self-heal hook. The canonical fleet updater wipes and
# re-copies the skill folder on a version bump, then runs the first of wire.sh / install.sh
# it finds at the skill root. Before this file existed nothing re-applied the install steps
# after an update, so a version bump left the executor-model config, the refreshed core-file
# blocks, and the jsonl sinks un-reapplied (a `.wired-vX` sentinel proved the loop visited the
# folder and found nothing to run).
#
# This re-runs the IDEMPOTENT install steps 03->06. Every step is guarded: a nonzero exit
# prints an operator WARNING but NEVER aborts the wire (this script always exits 0), so a
# single environment gap (e.g. no Chrome for step 06 on a headless box) cannot break a fleet
# update. Steps 00-02 (prereq probe, master-files locate, seed doc) are intentionally NOT
# re-run here: they are first-install/locate concerns, and 03-06 each resolve their own paths.
#
# Operator-only logging to stderr; no client-facing chatter (WE MOVE IN SILENCE).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$SCRIPT_DIR/scripts"
P="[skill 41][wire]"

run_step() {
  local script="$1"; shift || true
  local path="$STEPS_DIR/$script"
  if [[ ! -f "$path" ]]; then
    echo "$P SKIP $script (not present)" >&2
    return 0
  fi
  echo "$P run  $script ..." >&2
  if bash "$path" "$@"; then
    echo "$P OK   $script" >&2
  else
    echo "$P WARN $script exited nonzero -- continuing (fail-soft self-heal)" >&2
  fi
  return 0
}

echo "$P self-heal: re-applying idempotent install steps 03-06" >&2
run_step 03-init-jsonl-sinks.sh
run_step 04-update-core-files.sh
run_step 05-configure-executor-model.sh
run_step 06-verify-agent-browser.sh
echo "$P done (exit 0 always -- a wire failure never blocks a fleet update)" >&2
exit 0
