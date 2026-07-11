#!/usr/bin/env bash
# wire.sh — Skill 39 root re-wire (canonical updater hook, Skill-44 pattern).
#
# The canonical fleet updater copies this skill dir (wipe-and-replace) and then
# runs the skill's root wire.sh so the per-client wiring is re-applied exactly
# once per version. This re-runs the canonical install steps 00..08 — each behind
# its OWN existing idempotent guard — so the AGENTS/MEMORY/TOOLS blocks, crons,
# qualification templates, showing-scheduler scaffold, and the additive Skill-38
# RE extension are restored after an update without the operator re-running them.
#
# ALWAYS exits 0 (fail-soft): a single failing step (e.g. Skill 38 not yet
# present, MASTER_FILES_DIR not yet resolved) never aborts the rewire. Every step
# is idempotent and safe to re-run. Operator-verbose, no client-facing chatter.
# bash (not zsh).
#
# Scope note: the runtime worker scripts/property-lookup.sh is NOT an install
# step and is intentionally excluded. 08-update-core-files.sh is the SINGLE
# canonical AGENTS/MEMORY/TOOLS writer (the former duplicate AGENTS writer
# 04-update-agents-md.sh was folded into it and removed). MASTER_FILES_DIR
# propagates between steps via the persisted state file, so it need not be
# exported here.

set -uo pipefail

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS_DIR="$SKILL_ROOT/scripts"
P="[skill 39][wire]"

run_step() { # <script-name> — run an install step; never abort the rewire
  local script="$1"
  local path="$SCRIPTS_DIR/$script"
  if [ ! -f "$path" ]; then
    echo "$P SKIP $script (not found)"
    return 0
  fi
  echo "$P --- $script ---"
  if bash "$path"; then
    echo "$P OK   $script"
  else
    echo "$P WARN $script exited non-zero (continuing; rewire is fail-soft)"
  fi
  return 0
}

echo "$P re-wiring Skill 39 from $SKILL_ROOT (idempotent; fail-soft)"

# ── INDUSTRY GATE — HARD STOP (fix/industry-gate-and-idempotent-crons) ──────
# 00-verify-prerequisites.sh's exit code is captured DIRECTLY here — NOT
# through run_step(), which is fail-soft and swallows every non-zero exit into
# a WARN-and-continue. That swallowing is what made the old "Skill 39 REFUSES
# to proceed" claim toothless on the automated wire path: even a BLOCKED
# prereq check never stopped steps 01-08 from running. exit code 2 is the
# industry-gate's reserved "not real estate — skip this vertical" signal (see
# 00-verify-prerequisites.sh Section E / shared-utils/industry-gate.sh); on
# that code this rewire SKIPS steps 01-08 entirely and exits 0 cleanly (not an
# error — just "this box doesn't get the RE vertical"). Any OTHER exit code
# (0 = pass, 1 = a genuine hard-prereq gap like Skill 38 missing) falls through
# to the normal fail-soft run_step sequence below, unchanged from before.
_GATE_SCRIPT="$SCRIPTS_DIR/00-verify-prerequisites.sh"
if [ -f "$_GATE_SCRIPT" ]; then
  echo "$P --- 00-verify-prerequisites.sh (industry gate — hard stop on mismatch) ---"
  _GATE_OUT="$(bash "$_GATE_SCRIPT" 2>&1)"
  _GATE_RC=$?
  echo "$_GATE_OUT" | while IFS= read -r _line; do echo "$P     $_line"; done
  if [ "$_GATE_RC" -eq 2 ]; then
    echo "$P SKIP Skill 39 — box industry is not real estate; not wiring RE vertical (industry gate exit 2, hard stop)."
    echo "$P re-wire complete: SKIPPED (industry gate)."
    exit 0
  fi
  echo "$P OK   00-verify-prerequisites.sh (rc=$_GATE_RC; gate passed or a non-gate prereq gap — continuing fail-soft as before)"
else
  echo "$P SKIP 00-verify-prerequisites.sh (not found) — WARNING: industry gate could NOT run; proceeding fail-soft per pre-existing behavior."
fi

run_step 01-locate-master-files-folder.sh
run_step 02-configure-providers.sh
run_step 03-init-real-estate-events-log.sh
run_step 04-install-qualification-scripts.sh
run_step 05-install-sales-brain-extension.sh
run_step 06-scaffold-showing-scheduler.sh
run_step 07-register-crons.sh
run_step 08-update-core-files.sh

echo "$P re-wire complete (fail-soft; see per-step status above)."
exit 0
