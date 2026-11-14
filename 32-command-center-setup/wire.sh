#!/usr/bin/env bash
# 32-command-center-setup/wire.sh
# Per-skill wiring entry-point (picked up by the update-skills.sh wiring loop at
# highest priority: wire.sh > install.sh > setup-*.sh).
#
# What this does (idempotent):
#   Run scripts/materialize-dept-agents.sh so workspace department folders
#   become real runtime agents in openclaw.json agents.list[].
#
# Guard: skipped silently when no department workspace folders exist yet
# (materialize-dept-agents.sh itself exits 0 with a WARN in that case).
#
# Ordering: this runs inside the per-skill wiring loop, which executes BEFORE
# the explicit post-wiring apply-routing-fix.sh + materialize calls in the apply
# phase.  Both paths are idempotent; running twice is safe.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATERIALIZE="$SCRIPT_DIR/scripts/materialize-dept-agents.sh"

if [ ! -f "$MATERIALIZE" ]; then
  echo "  [wire/32] materialize-dept-agents.sh not found at $MATERIALIZE — skipping (older bundle?)"
  exit 0
fi

if [ ! -x "$MATERIALIZE" ]; then
  chmod +x "$MATERIALIZE" 2>/dev/null || true
fi

# A failure here is a real failure (CC-005): materialize-dept-agents.sh declares
# no "no departments yet" exit code (its documented codes are 0 = success and
# 1 = fatal; a box with no department folders exits 0 with a WARN), so any
# non-zero exit fails the wiring and the updater retries it, instead of the
# failure being recorded as success.
if bash "$MATERIALIZE"; then
  echo "  [wire/32] materialize-dept-agents: OK"
else
  echo "  [wire/32] materialize-dept-agents reported errors — failing this wiring so the updater retries"
  exit 1
fi
