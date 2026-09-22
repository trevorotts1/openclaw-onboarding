#!/usr/bin/env bash
# tests/unit/unify-backup-global-reclaim.test.sh
# -----------------------------------------------------------------------------
# Locks the END-OF-ROLL GLOBAL RECLAIM (reclaim_unify_backups, v25.1.74) that
# sits beside the per-target pruner locked by unify-backup-retention.test.sh.
#
# THE REMAINING FURNACE. v25.1.72/73 bounded each target's .bak-unify set, but
# the pruner only ever reaches a path the unify SCAN enumerated. That scan
# reads $OC_ROOT/workspaces, <workspace>/agents and <workspace>/departments,
# and keeps only dirs still carrying a live AGENTS.md / IDENTITY.md / SOUL.md.
# Measured on 6 client boxes 2026-09-22: 71,805 *.bak-unify-* files / ~8.4 GB,
# oldest 2026-06-07, still growing -- held in three populations the scan is
# structurally blind to:
#   1. ORPHANS      -- the dir's live core files are gone, so it fails the
#                      filter; its backlog is never reached again. Hidden
#                      archive dot-dirs are the same shape.
#   2. OUT OF TREE  -- <workspace>/zero-human-company/<co>/departments/... and
#                      ~/clawd/zero-human-company/<co>/departments/... are
#                      under neither agents/ nor departments/.
#   3. EARLY EXIT   -- a roll whose unify step refuses bounds nothing at all.
#
# WHAT THIS TEST PROVES (behavioral -- it runs the REAL extracted functions
# out of install.sh, never a re-implementation):
#   R1  an ORPHAN dir (backups present, every live core file gone) -> 3
#   R2  a hidden dot-dir archive with 5 backups -> 3
#   R3  the workspaces/ (plural) tree is reached
#   R4  the in-workspace zero-human-company/<co>/departments tree is reached
#   R5  the out-of-tree ~/clawd/zero-human-company tree is reached
#   R6  DECOY: AGENTS.md.bak-unify-notatimestamp is NEVER deleted, and neither
#       is a .bak-manual or a bare AGENTS.md.bak
#   R7  a LIVE AGENTS.md beside 5 backups survives; the backups become 3
#   R8  the python writer's same-second "-<n>" de-dupe suffix is reclaimed too
#   R9  UNIFY_BAK_KEEP=1 -> 1 kept; UNIFY_BAK_KEEP=0 -> none kept (the meaning
#       it already carries in both shipped pruners) and NO live file removed
#   R10 nested roots do not double-walk and over-delete (the workspace lives
#       INSIDE the OpenClaw root, so the same subtree is visited twice)
#   G1  REGRESSION: a second identical roll over unchanged content writes ZERO
#       new backups (an unconditional backup write would fail this)
#   G2  REGRESSION: install.sh defines AND calls reclaim_unify_backups
#   G3  REGRESSION: update-skills.sh defines AND calls reclaim_unify_backups
#
# Hermetic: a mktemp -d sandbox with HOME redirected into it, and a stub
# resolve_oc_root pinned to that sandbox -- the same seam update-skills.sh
# really uses (it sources shared-utils/resolve-oc-root.sh). No ~/.openclaw, no
# /data/.openclaw, no network, no fleet box, no writes into the checkout.
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
# Extract the REAL functions out of install.sh and source them. A guard that
# re-implements the code under test proves nothing, so these bodies are the
# shipped bodies, byte for byte.
# -----------------------------------------------------------------------------
FN_FILE="$SANDBOX/fn.sh"
RC_FILE="$SANDBOX/rc.sh"
awk '/^link_shared_core_files\(\) \{/{f=1} f{print} f && /^\}$/{exit}' \
    "$REPO_ROOT/install.sh" > "$FN_FILE"
awk '/^reclaim_unify_backups\(\) \{/{f=1} f{print} f && /^\}$/{exit}' \
    "$REPO_ROOT/install.sh" > "$RC_FILE"

if ! grep -q 'reclaim_unify_backups() {' "$RC_FILE"; then
  bad "extract: install.sh has no reclaim_unify_backups (end-of-roll reclaim missing?)"
  echo ""
  echo "=== unify-backup-global-reclaim: $PASS passed, $FAIL failed ==="
  exit 1
fi
if ! bash -n "$FN_FILE" || ! bash -n "$RC_FILE"; then
  bad "extract: an extracted function does not parse"
  echo ""
  echo "=== unify-backup-global-reclaim: $PASS passed, $FAIL failed ==="
  exit 1
fi

note() { :; }
warn() { :; }
# shellcheck disable=SC1090
. "$FN_FILE"
# shellcheck disable=SC1090
. "$RC_FILE"

OC_JSON="$SANDBOX/no-such-openclaw.json"
OC_WORKSPACE_DEFAULT="$SANDBOX/unused"
export HOME="$SANDBOX/home"
mkdir -p "$HOME"

# Pin the root resolver to the sandbox. reclaim_unify_backups prefers an
# already-defined resolve_oc_root (exactly how update-skills.sh gets it, by
# sourcing shared-utils/resolve-oc-root.sh), so this keeps the pass hermetic
# even when the machine running the suite genuinely has /data/.openclaw.
resolve_oc_root() { printf '%s\n' "$HOME/.openclaw"; }

OCROOT="$HOME/.openclaw"
CANON="$OCROOT/workspace"

seed5() {   # seed5 DIR FILENAME -> five backups with deterministic timestamps
  local d="$1" f="$2" t
  mkdir -p "$d"
  for t in 20250101-000001 20250102-000002 20250103-000003 20250104-000004 20250105-000005; do
    printf 'backup %s\n' "$t" > "$d/$f.bak-unify-$t"
  done
}
cnt() { ls -1d "$1"/"$2".bak-unify-* 2>/dev/null | wc -l | tr -d ' '; }

build_tree() {
  rm -rf "$OCROOT" "$HOME/clawd"
  mkdir -p "$CANON"
  printf 'CANONICAL BODY v1\n' > "$CANON/AGENTS.md"
  printf 'canonical tools\n'   > "$CANON/TOOLS.md"
  printf 'canonical user\n'    > "$CANON/USER.md"

  # A workspace the unify scan DOES reach -- the control for every leg below.
  CTL="$CANON/agents/alpha"
  mkdir -p "$CTL"; printf 'alpha identity\n' > "$CTL/IDENTITY.md"
  seed5 "$CTL" AGENTS.md

  # R1 ORPHAN: backups only, no live AGENTS.md / IDENTITY.md / SOUL.md.
  ORPH="$CANON/departments/sales/ghost-role"
  seed5 "$ORPH" AGENTS.md

  # R2 hidden dot-dir archive.
  DOTD="$CANON/departments/.billing-LEGACY-DUPLICATE-ARCHIVED"
  seed5 "$DOTD" AGENTS.md

  # R3 the workspaces/ (plural) tree.
  WSP="$OCROOT/workspaces/beta"
  mkdir -p "$WSP"; printf 'beta identity\n' > "$WSP/IDENTITY.md"
  seed5 "$WSP" TOOLS.md

  # R4 in-workspace zero-human-company tree.
  ZHC="$CANON/zero-human-company/acme/departments/sales/rep"
  mkdir -p "$ZHC"; printf 'rep identity\n' > "$ZHC/IDENTITY.md"
  seed5 "$ZHC" AGENTS.md

  # R5 out-of-tree ~/clawd tree.
  CLAWD="$HOME/clawd/zero-human-company/acme/departments/ops/lead"
  mkdir -p "$CLAWD"; printf 'lead identity\n' > "$CLAWD/IDENTITY.md"
  seed5 "$CLAWD" AGENTS.md

  # R6 decoys, in an orphan dir so only the reclaim can reach them.
  DEC="$CANON/departments/ops/decoys"
  seed5 "$DEC" AGENTS.md
  printf 'decoy\n' > "$DEC/AGENTS.md.bak-unify-notatimestamp"
  printf 'decoy\n' > "$DEC/AGENTS.md.bak-unify-2025010-00000"
  printf 'decoy\n' > "$DEC/AGENTS.md.bak-manual"
  printf 'decoy\n' > "$DEC/AGENTS.md.bak"

  # R7 a LIVE AGENTS.md beside 5 backups, in a dir the scan does NOT reach.
  LIVE="$CANON/zero-human-company/acme/departments/hr/lead"
  seed5 "$LIVE" AGENTS.md
  printf 'HAND EDITED LIVE BODY\n' > "$LIVE/AGENTS.md"

  # R8 the python writer's same-second "-<n>" de-dupe suffix.
  DUP="$CANON/departments/ops/dupes"
  seed5 "$DUP" AGENTS.md
  printf 'dupe\n' > "$DUP/AGENTS.md.bak-unify-20250106-000006-2"
  printf 'dupe\n' > "$DUP/AGENTS.md.bak-unify-20250106-000006-3"
}

run_reclaim() { WORKSPACE_DIR="$CANON" reclaim_unify_backups >/dev/null 2>&1 || true; }

# -----------------------------------------------------------------------------
hdr "R1-R5, R8, R10 -- every population the unify scan cannot see is bounded"
# -----------------------------------------------------------------------------
build_tree
run_reclaim

N="$(cnt "$CTL" AGENTS.md)"
[ "$N" = "3" ] && ok "R10: the scanned control dir is 3, not over-deleted by nested roots" \
               || bad "R10: control dir expected 3, got $N (nested roots double-walked?)"
N="$(cnt "$ORPH" AGENTS.md)"
[ "$N" = "3" ] && ok "R1: ORPHAN dir (no live core file) reclaimed to 3" \
               || bad "R1: ORPHAN dir expected 3, got $N"
N="$(cnt "$DOTD" AGENTS.md)"
[ "$N" = "3" ] && ok "R2: hidden dot-dir archive reclaimed to 3" \
               || bad "R2: hidden dot-dir expected 3, got $N"
N="$(cnt "$WSP" TOOLS.md)"
[ "$N" = "3" ] && ok "R3: the workspaces/ (plural) tree is reached" \
               || bad "R3: workspaces/ tree expected 3, got $N"
N="$(cnt "$ZHC" AGENTS.md)"
[ "$N" = "3" ] && ok "R4: workspace/zero-human-company/<co>/departments is reached" \
               || bad "R4: zero-human-company tree expected 3, got $N"
N="$(cnt "$CLAWD" AGENTS.md)"
[ "$N" = "3" ] && ok "R5: out-of-tree ~/clawd/zero-human-company is reached" \
               || bad "R5: ~/clawd tree expected 3, got $N"

# The two "-<n>" suffixes sort newest, so they plus the newest bare timestamp
# are the three that survive.
N="$(cnt "$DUP" AGENTS.md)"
[ "$N" = "3" ] && ok "R8: the '-<n>' same-second de-dupe suffix is counted and reclaimed" \
               || bad "R8: '-<n>' suffix group expected 3, got $N"
if [ -e "$DUP/AGENTS.md.bak-unify-20250106-000006-3" ]; then
  ok "R8: the NEWEST backup survived the '-<n>' ordering"
else
  bad "R8: the newest '-<n>' backup was deleted (sort order wrong)"
fi

# -----------------------------------------------------------------------------
hdr "R6 -- nothing outside the <ts> pattern is ever deleted"
# -----------------------------------------------------------------------------
N="$(cnt "$DEC" AGENTS.md)"
# 3 real survivors + the two non-timestamp decoys the glob also matches.
[ "$N" = "5" ] && ok "R6: the timestamped set is 3 and both non-timestamp decoys remain" \
               || bad "R6: decoy dir expected 5 glob hits (3 kept + 2 decoys), got $N"
for d in AGENTS.md.bak-unify-notatimestamp AGENTS.md.bak-unify-2025010-00000 \
         AGENTS.md.bak-manual AGENTS.md.bak; do
  [ -e "$DEC/$d" ] && ok "R6: $d survived" || bad "R6: $d was DELETED"
done

# -----------------------------------------------------------------------------
hdr "R7 -- a live core file survives; only its backups are bounded"
# -----------------------------------------------------------------------------
if [ -f "$LIVE/AGENTS.md" ] && [ "$(cat "$LIVE/AGENTS.md")" = "HAND EDITED LIVE BODY" ]; then
  ok "R7: the live AGENTS.md survived untouched"
else
  bad "R7: the live AGENTS.md was deleted or rewritten by the reclaim"
fi
N="$(cnt "$LIVE" AGENTS.md)"
[ "$N" = "3" ] && ok "R7: its 5 backups were reduced to 3" \
               || bad "R7: expected 3 backups beside the live file, got $N"
for keepfile in AGENTS.md.bak-unify-20250103-000003 \
                AGENTS.md.bak-unify-20250104-000004 \
                AGENTS.md.bak-unify-20250105-000005; do
  [ -e "$LIVE/$keepfile" ] && ok "R7: the NEWEST backup $keepfile was kept" \
                           || bad "R7: $keepfile (one of the 3 newest) was deleted"
done

# -----------------------------------------------------------------------------
hdr "R9 -- UNIFY_BAK_KEEP is the single retention knob"
# -----------------------------------------------------------------------------
build_tree
UNIFY_BAK_KEEP=1 run_reclaim
N="$(cnt "$ORPH" AGENTS.md)"
[ "$N" = "1" ] && ok "R9: UNIFY_BAK_KEEP=1 -> 1 backup kept" \
               || bad "R9: UNIFY_BAK_KEEP=1 -> expected 1, got $N"

build_tree
UNIFY_BAK_KEEP=0 run_reclaim
N="$(cnt "$ORPH" AGENTS.md)"
[ "$N" = "0" ] && ok "R9: UNIFY_BAK_KEEP=0 -> no backups kept (its documented meaning)" \
               || bad "R9: UNIFY_BAK_KEEP=0 -> expected 0, got $N"
if [ -f "$LIVE/AGENTS.md" ] && [ -f "$CANON/AGENTS.md" ]; then
  ok "R9: UNIFY_BAK_KEEP=0 removed backups ONLY -- every live core file survived"
else
  bad "R9: UNIFY_BAK_KEEP=0 removed a LIVE core file"
fi
for d in AGENTS.md.bak-unify-notatimestamp AGENTS.md.bak-manual; do
  [ -e "$DEC/$d" ] && ok "R9: UNIFY_BAK_KEEP=0 still refused the decoy $d" \
                   || bad "R9: UNIFY_BAK_KEEP=0 deleted the decoy $d"
done

build_tree
UNIFY_BAK_KEEP=not-a-number run_reclaim
N="$(cnt "$ORPH" AGENTS.md)"
[ "$N" = "3" ] && ok "R9: a garbage UNIFY_BAK_KEEP falls back to the default 3" \
               || bad "R9: garbage UNIFY_BAK_KEEP -> expected 3, got $N"

# -----------------------------------------------------------------------------
hdr "G1 -- REGRESSION: an unchanged second roll writes NO new backup"
# An unconditional backup write (the original v25.1.71 defect) fails this leg.
# -----------------------------------------------------------------------------
build_tree
rm -f "$CTL"/AGENTS.md.bak-unify-*
printf 'AGENT-OWN DIVERGENT BODY\n' > "$CTL/AGENTS.md"
link_shared_core_files "$CANON" >/dev/null 2>&1 || true
N1="$(cnt "$CTL" AGENTS.md)"
[ "$N1" = "1" ] && ok "G1: a real divergence writes exactly 1 backup (guard is live)" \
                || bad "G1: divergent file -> expected 1 backup, got $N1"
link_shared_core_files "$CANON" >/dev/null 2>&1 || true
link_shared_core_files "$CANON" >/dev/null 2>&1 || true
N2="$(cnt "$CTL" AGENTS.md)"
[ "$N2" = "1" ] && ok "G1: two further rolls over unchanged content wrote ZERO new backups" \
                || bad "G1: unchanged rolls churned backups (expected 1, got $N2)"

# -----------------------------------------------------------------------------
hdr "G2/G3 -- REGRESSION: both scripts define AND call the end-of-roll reclaim"
# Removing either call site turns these red -- proven non-vacuous before merge.
# -----------------------------------------------------------------------------
IS="$REPO_ROOT/install.sh"
US="$REPO_ROOT/update-skills.sh"

grep -q '^reclaim_unify_backups() {' "$IS" \
  && ok "G2: install.sh defines reclaim_unify_backups" \
  || bad "G2: install.sh has NO reclaim_unify_backups definition"
grep -qE '^[[:space:]]*reclaim_unify_backups( \|\| true)?[[:space:]]*$' "$IS" \
  && ok "G2: install.sh CALLS reclaim_unify_backups at the end of the roll" \
  || bad "G2: install.sh never calls reclaim_unify_backups (end-of-roll reclaim removed)"

grep -q '^reclaim_unify_backups() {' "$US" \
  && ok "G3: update-skills.sh defines reclaim_unify_backups" \
  || bad "G3: update-skills.sh has NO reclaim_unify_backups definition (the two copies drifted)"
grep -qE '^[[:space:]]*reclaim_unify_backups( \|\| true)?[[:space:]]*$' "$US" \
  && ok "G3: update-skills.sh CALLS reclaim_unify_backups at the end of the roll" \
  || bad "G3: update-skills.sh never calls reclaim_unify_backups (end-of-roll reclaim removed)"

grep -q 'UNIFY_BAK_KEEP' "$IS" && grep -q 'UNIFY_BAK_KEEP' "$US" \
  && ok "G2/G3: both scripts still honour the single UNIFY_BAK_KEEP knob" \
  || bad "G2/G3: UNIFY_BAK_KEEP missing from a script"

echo ""
echo "=== unify-backup-global-reclaim: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
