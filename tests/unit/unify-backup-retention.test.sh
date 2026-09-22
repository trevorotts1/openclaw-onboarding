#!/usr/bin/env bash
# tests/unit/unify-backup-retention.test.sh
# -----------------------------------------------------------------------------
# Locks the .bak-unify retention contract for the shared-core-file unification
# (N29 / link_shared_core_files in install.sh + update-skills.sh, and the
# department-tree AGENTS.md passes in create_role_workspaces.py).
#
# THE FURNACE THIS LOCKS. The unify step backed up a divergent core file to
# <file>.bak-unify-<ts> and kept EVERY backup forever. A canonical file that
# differs between rolls therefore left one FULL-SIZE copy per target per roll.
# Measured live on a client Mac Mini 2026-09-21: 25,604 AGENTS.md.bak-unify-*
# files / 4.3 GB across the department tree, written daily since 2026-06-23,
# with the disk at 95%. Nothing in the code path ever deleted one.
#
# WHAT THIS TEST PROVES (behavioral -- it runs the REAL extracted code):
#   T1  a second unify run over an unchanged tree creates NO new backup
#   T2  a real content change DOES create a backup (T1 is not a dead pruner)
#   T3  the 5th backup prunes the set to 3 -- and the 3 kept are the NEWEST
#   T4  UNIFY_BAK_KEEP overrides the retention count
#   T5  ANTI-FALSE-POSITIVE: the pruner touches ONLY this target's own
#       .bak-unify-* files (a sibling file's backups and a non-unify backup
#       both survive)
#   T6  PARITY: update-skills.sh carries the same helper AND calls it
#   T7  the python department-tree writer de-dupes and prunes the same way
#
# Hermetic: mktemp -d sandbox, HOME redirected into it. No ~/.openclaw, no
# network, no fleet box, no writes anywhere in the checkout.
# bash 3.2 safe: no associative arrays, no mapfile, no case modifiers.
# Exit 0 = all pass, 1 = at least one failure.
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }
hdr() { printf '\n== %s ==\n' "$1"; }

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Extract the REAL link_shared_core_files() out of install.sh and source it.
# A guard that re-implements the function under test proves nothing, so the
# body here is the shipped body, byte for byte.
# -----------------------------------------------------------------------------
FN_FILE="$SANDBOX/fn.sh"
awk '/^link_shared_core_files\(\) \{/{f=1} f{print} f && /^\}$/{exit}' \
    "$REPO_ROOT/install.sh" > "$FN_FILE"

if ! grep -q '_lsc_prune_baks' "$FN_FILE"; then
  bad "extract: install.sh link_shared_core_files has no _lsc_prune_baks (fix missing?)"
  echo ""
  echo "=== unify-backup-retention: $PASS passed, $FAIL failed ==="
  exit 1
fi
if ! bash -n "$FN_FILE"; then
  bad "extract: the extracted function does not parse"
  exit 1
fi

note() { :; }
warn() { :; }
# shellcheck disable=SC1090
. "$FN_FILE"

OC_JSON="$SANDBOX/no-such-openclaw.json"
OC_WORKSPACE_DEFAULT="$SANDBOX/unused"
export HOME="$SANDBOX/home"
mkdir -p "$HOME"

CANON="$SANDBOX/ws"
AGENT="$CANON/agents/alpha"
TARGET="$AGENT/AGENTS.md"

reset_tree() {
  rm -rf "$CANON"
  mkdir -p "$AGENT"
  printf 'CANONICAL BODY v1\n' > "$CANON/AGENTS.md"
  printf 'canonical tools\n'   > "$CANON/TOOLS.md"
  printf 'canonical user\n'    > "$CANON/USER.md"
  printf 'alpha identity\n'    > "$AGENT/IDENTITY.md"
  printf 'AGENT-OWN DIVERGENT BODY\n' > "$TARGET"
  printf 'canonical tools\n'   > "$AGENT/TOOLS.md"
  printf 'canonical user\n'    > "$AGENT/USER.md"
}

run_unify() { link_shared_core_files "$CANON" >/dev/null 2>&1 || true; }

count_baks() { ls -1d "$TARGET".bak-unify-* 2>/dev/null | wc -l | tr -d ' '; }

# -----------------------------------------------------------------------------
hdr "T1/T2 -- a backup is written for a real change, and only for a real change"
# -----------------------------------------------------------------------------
reset_tree
run_unify
N1="$(count_baks)"
[ "$N1" = "1" ] && ok "T2: divergent file -> exactly 1 backup" \
                || bad "T2: divergent file -> expected 1 backup, got $N1"
if [ "$(cat "$TARGET")" = "CANONICAL BODY v1" ]; then
  ok "T2: target was rewritten with canonical content"
else
  bad "T2: target was NOT rewritten with canonical content"
fi

run_unify
run_unify
N2="$(count_baks)"
[ "$N2" = "1" ] && ok "T1: two further runs over an unchanged tree -> still 1 backup" \
                || bad "T1: unchanged tree churned backups (expected 1, got $N2)"

# -----------------------------------------------------------------------------
hdr "T3 -- the 5th backup prunes the set to 3 newest"
# -----------------------------------------------------------------------------
reset_tree
# Seed four older backups with distinct, deterministic timestamps. The unify
# run below adds today's, which sorts newest.
for t in 20250101-000001 20250101-000002 20250101-000003 20250101-000004; do
  printf 'old backup %s\n' "$t" > "$TARGET.bak-unify-$t"
done
# Sibling + non-unify decoys for T5.
printf 'other file backup\n' > "$AGENT/TOOLS.md.bak-unify-20250101-000001"
printf 'manual backup\n'     > "$TARGET.bak-manual"

run_unify
N3="$(count_baks)"
[ "$N3" = "3" ] && ok "T3: 5 backups pruned to 3" \
                || bad "T3: expected 3 backups after prune, got $N3"

if [ -e "$TARGET.bak-unify-20250101-000001" ] || [ -e "$TARGET.bak-unify-20250101-000002" ]; then
  bad "T3: oldest backups were not the ones deleted"
else
  ok "T3: the two OLDEST backups were the ones deleted"
fi
if [ -e "$TARGET.bak-unify-20250101-000003" ] && [ -e "$TARGET.bak-unify-20250101-000004" ]; then
  ok "T3: the newest seeded backups were kept"
else
  bad "T3: a newer seeded backup was deleted"
fi

# -----------------------------------------------------------------------------
hdr "T5 -- the pruner touches nothing but this target's own unify backups"
# -----------------------------------------------------------------------------
[ -e "$AGENT/TOOLS.md.bak-unify-20250101-000001" ] \
  && ok "T5: a SIBLING file's .bak-unify survived" \
  || bad "T5: the pruner deleted another file's .bak-unify"
[ -e "$TARGET.bak-manual" ] \
  && ok "T5: a non-unify backup of the same target survived" \
  || bad "T5: the pruner deleted a non-unify backup"

# -----------------------------------------------------------------------------
hdr "T4 -- UNIFY_BAK_KEEP overrides the retention count"
# -----------------------------------------------------------------------------
reset_tree
for t in 20250101-000001 20250101-000002 20250101-000003 20250101-000004; do
  printf 'old backup %s\n' "$t" > "$TARGET.bak-unify-$t"
done
UNIFY_BAK_KEEP=1 run_unify
N4="$(count_baks)"
[ "$N4" = "1" ] && ok "T4: UNIFY_BAK_KEEP=1 -> 1 backup kept" \
                || bad "T4: UNIFY_BAK_KEEP=1 -> expected 1, got $N4"

reset_tree
for t in 20250101-000001 20250101-000002 20250101-000003 20250101-000004; do
  printf 'old backup %s\n' "$t" > "$TARGET.bak-unify-$t"
done
UNIFY_BAK_KEEP=not-a-number run_unify
N4B="$(count_baks)"
[ "$N4B" = "3" ] && ok "T4: a garbage UNIFY_BAK_KEEP falls back to the default 3" \
                 || bad "T4: garbage UNIFY_BAK_KEEP -> expected 3, got $N4B"

# -----------------------------------------------------------------------------
hdr "T6 -- PARITY: update-skills.sh carries the same helper and calls it"
# -----------------------------------------------------------------------------
US="$REPO_ROOT/update-skills.sh"
grep -q '_lsc_prune_baks() {' "$US" \
  && ok "T6: update-skills.sh defines _lsc_prune_baks" \
  || bad "T6: update-skills.sh has NO _lsc_prune_baks (the two copies drifted)"
grep -q '_NPRUNED="$(_lsc_prune_baks "$LINKPATH")"' "$US" \
  && ok "T6: update-skills.sh calls the pruner after a backup" \
  || bad "T6: update-skills.sh never calls _lsc_prune_baks"
grep -q 'UNIFY_BAK_KEEP' "$US" \
  && ok "T6: update-skills.sh honours UNIFY_BAK_KEEP" \
  || bad "T6: update-skills.sh has no UNIFY_BAK_KEEP override"

# -----------------------------------------------------------------------------
hdr "T7 -- the python department-tree writer de-dupes and prunes"
# -----------------------------------------------------------------------------
if REPO_ROOT="$REPO_ROOT" SANDBOX="$SANDBOX" python3 "$REPO_ROOT/tests/unit/unify_backup_retention_py.py"; then
  ok "T7: create_role_workspaces.py _unify_backup de-dupes + prunes"
else
  bad "T7: create_role_workspaces.py _unify_backup failed its checks"
fi

echo ""
echo "=== unify-backup-retention: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
