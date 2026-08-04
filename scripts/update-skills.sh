#!/usr/bin/env bash
# scripts/update-skills.sh — RETIRED. This path is NOT the updater. Do not run it.
# ============================================================================
# THE DEFECT THIS FILE FIXES (repo-wide fatal)
#
# Two files shared the name "update-skills.sh":
#   - update-skills.sh          (repo root)  — the REAL, actively-maintained
#     updater. Content-aware A3 gate, exit-2 FATAL semantics, stale-PENDING
#     sweep, CORE_UPDATES wiring, MCP registration, Command Center refresh,
#     the full onboarding-state.sh verification gate — every v21.7.x fix.
#   - scripts/update-skills.sh  (THIS path)  — a much smaller, independently
#     maintained "surgical update" script that never received any of the
#     v21.7.x work. It COULD be invoked successfully (it ran, it copied some
#     files, it bumped its own local .onboarding-version stamp) while
#     silently skipping the manifest/stamp pipeline, the CORE_UPDATES wiring,
#     the AGENTS.md pointer-stanza rewrite, and every gate the real updater
#     carries.
#
# Two boxes' worth of pilots ran THIS script — because a stale crontab,
# an old doc, or plain muscle-memory pointed at "scripts/update-skills.sh" —
# and got a byte-identical AGENTS.md every single week while the version
# stamp climbed. That is a HOLLOW UPDATE reported as a success: the single
# worst failure mode an updater can have, because nothing about the run
# looked wrong.
#
# THE FIX
# A wrong invocation of an updater must FAIL LOUDLY. It must never again be
# possible for this path to quietly do a little bit of work and exit 0. So
# this file is retired: it no longer updates anything. It identifies itself,
# tells you exactly which script to run instead, and exits non-zero — every
# single time, unconditionally, on every platform. There is no flag, no env
# var, and no code path in this file that returns 0.
#
# WHAT TO RUN INSTEAD
#   The canonical updater lives at the REPO ROOT:
#     https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh
#   A box's weekly cron should invoke it via the wrapper scripts/setup-weekly-
#   update.sh installs ($HOME/.openclaw/skills/.update-restart-if-needed),
#   which always curls the LATEST root script rather than running any local
#   copy (stale or otherwise). See UPDATE-PLAYBOOK.md.
#
# CI ENFORCEMENT
#   .github/workflows/single-update-skills-entrypoint-guard.yml +
#   scripts/test-single-update-skills-entrypoint.sh fail the build if this
#   file is ever restored to doing real update work, or if any doc/script/
#   cron template in this repo references this path as something to run.
# ============================================================================
set -uo pipefail

SELF="$(basename "${BASH_SOURCE[0]:-$0}")"
ROOT_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh"

# Best-effort: if this bundle also carries the real root script one directory
# up (the normal shape of a downloaded/cloned repo), name its on-disk path too
# — that is the fastest fix for whoever hit this.
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
_ROOT_LOCAL=""
if [ -n "$_HERE" ] && [ -f "$_HERE/../update-skills.sh" ]; then
  _ROOT_LOCAL="$(cd "$_HERE/.." && pwd)/update-skills.sh"
fi

{
  echo ""
  echo "############################################################"
  echo "## RETIRED: $SELF does not update anything."
  echo "## This path was a second, unmaintained updater. It is retired"
  echo "## on purpose so a stale invocation FAILS instead of silently"
  echo "## doing partial work and reporting success."
  echo "##"
  echo "## RUN THIS INSTEAD (the real, actively-maintained updater):"
  if [ -n "$_ROOT_LOCAL" ]; then
    echo "##   bash \"$_ROOT_LOCAL\""
  fi
  echo "##   curl -fsSL $ROOT_URL | bash"
  echo "##"
  echo "## If a crontab, a doc, or an installer on this box still points at"
  echo "## \"scripts/update-skills.sh\", that reference is stale — repoint it"
  echo "## at the root update-skills.sh (see UPDATE-PLAYBOOK.md). A fresh"
  echo "## root-script run self-heals the common case: the weekly cron"
  echo "## wrapper installed by scripts/setup-weekly-update.sh."
  echo "############################################################"
  echo ""
} >&2

exit 1
