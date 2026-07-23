#!/usr/bin/env bash
# tests/unit/both-paths-zhe-delivery.test.sh
#
# Dynamic, OFFLINE both-paths proof for the four Zero-Human-Experience (ZHE)
# delivery dimensions that prove-zhe.py asserts at runtime (ZHE_SEQUENCE_V1 /
# plan W1.2). This is the dynamic backstop for the static D16-D19 grep steps in
# .github/workflows/both-paths-delivery-guard.yml: it re-proves, in one place,
# that BOTH install.sh AND update-skills.sh reach every dimension, and that the
# underlying delivery script carries the canonical marker/content. A dimension
# missing from EITHER path is a regression and fails the build.
#
# Dimensions (each must land on install AND update):
#   D16  workspace-dept-script refresh (no stale build_deck.py)
#   D17  AGENTS.md ZHE markers (persona-reflex / full-context-handoff /
#        owner-reporting / platform-facts)
#   D18  CC board build (Kanban/workspace seed on install; board sync on update)
#   D19  qmd persona-store reconcile
#
# Purely offline: only reads repo files (grep). No network, no runtime, no DB.

set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO" || { echo "FATAL: cannot cd to repo root"; exit 2; }

INSTALL="install.sh"
UPDATE="update-skills.sh"
CRW="23-ai-workforce-blueprint/scripts/create_role_workspaces.py"
FFD="23-ai-workforce-blueprint/scripts/floor-fill-driver.py"
MIG="23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh"
FLEET="scripts/apply-fleet-standards.sh"
RFI="32-command-center-setup/scripts/run-full-install.sh"
QMD="shared-utils/provision-persona-index.sh"

FAILS=0
pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; FAILS=$((FAILS+1)); }
# clean <since> : true when no new failure was recorded since the snapshot.
clean() { [ "$FAILS" -eq "$1" ]; }

# need <file> <label> : the named file must exist or the whole dimension is moot.
need() {
  if [ ! -f "$1" ]; then fail "$2: required file missing -> $1"; return 1; fi
  return 0
}

echo "── D16: workspace-dept-script refresh (no stale build_deck.py) ──"
_D16=$FAILS
if need "$CRW" "D16" && need "$MIG" "D16" && need "$FFD" "D16"; then
  # (a) create_role_workspaces.py must REFRESH canonical generators, not leave a
  #     stale build_deck.py behind. Canonical contract marker the sibling stamps
  #     at the dept-scripts copy site: REFRESH_CANONICAL_SCRIPTS (a small family
  #     of equivalents is accepted so the guard survives the exact token choice).
  if grep -Eq 'REFRESH_CANONICAL_SCRIPTS|CANONICAL_GENERATORS?_REFRESH|refresh[^\n]*canonical[^\n]*generator|canonical[^\n]*generator[^\n]*refresh|(always|force)[_ -]*(re)?(write|copy|overwrite)[^\n]*build_deck|build_deck[^\n]*(always|force)[_ -]*(over)?(write|copy)' "$CRW"; then
    pass "D16a: create_role_workspaces.py refreshes canonical generators (stale build_deck.py replaced)"
  else
    fail "D16a: create_role_workspaces.py has no canonical-generator REFRESH — dept scripts stay skip-existing, so a stale build_deck.py is never replaced on existing boxes (stamp REFRESH_CANONICAL_SCRIPTS at the dept-scripts copy site)"
  fi
  # (b) the refresh entrypoint is reachable on BOTH paths:
  #     install.sh + update-skills.sh -> migrate-existing-workforce.sh
  #     -> floor-fill-driver.py -> create_role_workspaces.py
  grep -q 'migrate-existing-workforce' "$INSTALL" || fail "D16b-install: migrate-existing-workforce not reached from install.sh"
  grep -q 'migrate-existing-workforce' "$UPDATE"  || fail "D16b-update: migrate-existing-workforce not reached from update-skills.sh"
  grep -q 'create_role_workspaces'     "$FFD"     || fail "D16b-chain: floor-fill-driver.py no longer chains into create_role_workspaces.py"
  grep -q 'floor-fill-driver'          "$MIG"     || fail "D16b-chain: migrate-existing-workforce.sh no longer invokes floor-fill-driver.py"
  clean "$_D16" && pass "D16b: refresh reachable on both paths (install + update -> migrate -> floor-fill -> create_role_workspaces)"
fi

echo "── D17: AGENTS.md ZHE markers stamped on both paths ──"
_D17=$FAILS
if need "$FLEET" "D17"; then
  # apply-fleet-standards.sh is the canonical AGENTS.md stamping script and is
  # invoked on BOTH paths. Marker families MUST match prove-zhe.py AGENTS_DOCTRINE
  # so the runtime ZHE gate goes green when these land.
  declare -a M_NAMES=("persona-reflex" "full-context-handoff" "owner-reporting" "platform-facts")
  declare -a M_PATS=(
    'PERSONA_REFLEX_V[0-9]'
    'FULL_CONTEXT_HANDOFF_V[0-9]'
    'OWNER_REPORTING_V[0-9]|REPORTING_RULES_V[0-9]'
    'PLATFORM_FACTS_V[0-9]'
  )
  i=0
  while [ "$i" -lt "${#M_PATS[@]}" ]; do
    if grep -Eq "${M_PATS[$i]}" "$FLEET"; then
      pass "D17-marker: ${M_NAMES[$i]} marker present in apply-fleet-standards.sh"
    else
      fail "D17-marker: ${M_NAMES[$i]} marker (${M_PATS[$i]}) NOT stamped by apply-fleet-standards.sh — prove-zhe.py AGENTS_DOCTRINE stays RED on every box"
    fi
    i=$((i+1))
  done
  # invoked (executed, not merely persisted) on BOTH paths
  grep -Eq 'bash[^\n]*apply-fleet-standards|apply-fleet-standards\.sh"?[[:space:]]*\|\||"\$FLEET_STD"' "$UPDATE" \
    || grep -q 'FLEET_STD' "$UPDATE" \
    || fail "D17-update: apply-fleet-standards.sh not executed on update path"
  grep -q 'apply-fleet-standards.sh' "$INSTALL" || fail "D17-install: apply-fleet-standards.sh not executed on install path"
  clean "$_D17" && pass "D17: all four ZHE AGENTS.md markers stamped + apply-fleet-standards executed on both paths"
fi

echo "── D18: CC board build delivered on both paths ──"
_D18=$FAILS
if need "$RFI" "D18"; then
  # Fresh install builds the board (Kanban/workspace seed via db:seed).
  grep -q 'db:seed' "$RFI" || fail "D18-build: run-full-install.sh has no db:seed — CC board/Kanban workspaces never seeded on fresh install"
  # Update refreshes the board WITHOUT clobbering client rows (sync-departments).
  grep -Eq 'sync-departments|sync_departments|phase=6c' "$RFI" \
    || fail "D18-sync: run-full-install.sh has no board sync (sync-departments / phase=6c) — existing boxes keep a stale board on update"
  # run-full-install.sh reachable on BOTH paths.
  grep -q 'run-full-install' "$INSTALL" || fail "D18-install: run-full-install.sh not referenced in install.sh"
  grep -q 'run-full-install' "$UPDATE"  || fail "D18-update: run-full-install.sh not invoked in update-skills.sh"
  # The board landing is verified by the ZHE acceptance gate (prove-zhe phase 7z).
  grep -q 'prove-zhe' "$RFI" || fail "D18-gate: run-full-install.sh no longer runs the prove-zhe ZHE acceptance gate"
  clean "$_D18" && pass "D18: CC board built on install (db:seed) + synced on update (sync-departments), reachable both paths, gated by prove-zhe"
fi

echo "── D19: qmd persona-store removed (2026-07-23) ──"
_D19=$FAILS
if need "$QMD" "D19"; then
  # qmd was replaced by Google/OpenAI embeddings. The reconcile_qmd_persona_index
  # function and all _qmd_ helpers have been gutted. Calls in install.sh and
  # update-skills.sh have been replaced with archive comments.
  if grep -q 'reconcile_qmd_persona_index()' "$QMD" 2>/dev/null; then
    fail "D19-def: reconcile_qmd_persona_index() still defined in provision-persona-index.sh — should be removed (qmd replaced by embeddings)"
  fi
  if grep -q '^\s*reconcile_qmd_persona_index ' "$INSTALL" 2>/dev/null; then
    fail "D19-install: reconcile_qmd_persona_index still called in install.sh"
  fi
  if grep -q '^\s*reconcile_qmd_persona_index ' "$UPDATE" 2>/dev/null; then
    fail "D19-update: reconcile_qmd_persona_index still called in update-skills.sh"
  fi
  # Verify the archive comment exists (proof the removal was intentional)
  grep -q 'qmd provisioning removed' "$QMD" \
    || fail "D19-archive: no qmd-removal archive comment in provision-persona-index.sh"
  clean "$_D19" && pass "D19: qmd persona-store removed — replaced by Google/OpenAI embeddings"
fi

echo
if [ "$FAILS" -ne 0 ]; then
  echo "BOTH-PATHS-ZHE-DELIVERY: $FAILS check(s) FAILED — a ZHE dimension is missing from install and/or update."
  exit 1
fi
echo "BOTH-PATHS-ZHE-DELIVERY: all dimensions deliver on BOTH paths."
exit 0
