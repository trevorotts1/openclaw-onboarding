#!/usr/bin/env bash
# ============================================================================
# updater-guarded-skill-removal.test.sh
#
# THE DEFECT THIS LOCKS (measured 2026-09-17, controlled reproduction on a
# Hostinger VPS). update-skills.sh runs under `set -euo pipefail`. Its skill
# install loop removed each old skill with a bare
#   rm -rf "$SKILLS_DIR/$SKILL_NAME"
# Root-owned __pycache__ directories under
# skills/23-ai-workforce-blueprint/scripts/ and skills/shared-utils/ made that
# rm return 1 AFTER it had already deleted everything it could reach. `set -e`
# then exited the updater on the spot with NO message. Skill 23 was left
# holding 3 of its 1934 files, no version stamp was written, and the log
# contained no error text at all.
#
# MECHANISM. On POSIX, unlinking a file needs write+execute on its PARENT
# DIRECTORY; the file's own owner and mode are irrelevant. The blocker is
# therefore the root-owned __pycache__ DIRECTORY, not the root-owned .pyc. The
# fixtures below reproduce exactly that with a mode-0555 directory, which is
# the same permission shape without needing root.
#
# THE CONTRACT UNDER TEST
#   1. The removability scan probes with a REAL write attempt, never `-w`.
#   2. A blocked tree is refused BEFORE anything is deleted: the tree is
#      byte-for-byte untouched after the refusal.
#   3. A refusal prints exactly ONE PERMISSION BLOCK line, naming the path,
#      the owner, the running user and a recursive chown remedy.
#   4. The write pre-flight refuses the whole run up front, with exit 1, when
#      any installed skill tree is unremovable.
#   5. KNOWN-GOOD CONTROLS, run FIRST in every case: an identical removable
#      fixture scans clean, is really removed, and lets the pre-flight pass.
#      Without them a broken probe would make every negative pass for the
#      wrong reason.
#   6. FIXTURE CONTROL: a bare `rm -rf` on the blocked fixture really does
#      fail and really does gut the tree. If that stops being true the
#      fixture no longer reproduces the defect and this suite is testing
#      nothing.
#   7. update-skills.sh carries no bare skill-tree `rm -rf` any more, and
#      exports PYTHONDONTWRITEBYTECODE before it runs any python.
#   8. An unremovable __pycache__ is self-healed, not refused: the removal
#      deletes everything around it and the pre-flight passes.
#
# METHOD. Nothing is reimplemented. The shell block is EXTRACTED VERBATIM from
# update-skills.sh between the same markers PR 1187 established; if a marker
# drifts or vanishes this suite exits 2 rather than silently testing nothing.
#
# SAFETY. Every case runs inside mktemp -d. No network, no box, no SSH, and
# nothing outside the temp tree is opened for writing or removed.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
TARGET="$REPO/update-skills.sh"
LOOPACT="$REPO/scripts/activate-loop-protection.sh"

PASS=0; FAIL=0; SKIP=0
ok()   { printf '  PASS: %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL+1)); }
skip() { printf '  SKIP: %s\n' "$1"; SKIP=$((SKIP+1)); }
hdr()  { printf '\n== %s ==\n' "$1"; }

[ -f "$TARGET" ] || { echo "FATAL: $TARGET not found"; exit 2; }

WORK="$(mktemp -d)"
trap 'chmod -R u+rwX "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT

AM_ROOT=0
[ "$(id -u)" = "0" ] && AM_ROOT=1

extract_block() {
  awk -v b=">>> $1-BEGIN" -v e="<<< $1-END" '
    index($0, b) { p=1 }
    index($0, e) { p=0 }
    p { print }
  ' "$TARGET"
}

# A skill tree shaped like the real one: a scripts/ dir with a __pycache__
# under it, which is exactly where the root-owned bytecode landed.
make_skill() {
  local root="$1"
  mkdir -p "$root/scripts/__pycache__" "$root/references"
  printf '# skill\n'      > "$root/SKILL.md"
  printf '# install\n'    > "$root/INSTALL.md"
  printf 'x = 1\n'        > "$root/scripts/tool.py"
  printf 'cached\n'       > "$root/scripts/__pycache__/tool.cpython-311.pyc"
  printf 'ref\n'          > "$root/references/notes.md"
}
count_files() { find "$1" 2>/dev/null | wc -l | tr -d ' '; }

hdr "(0) the markers still exist, so this suite cannot silently test nothing"
extract_block WRITE-PREFLIGHT > "$WORK/preflight.sh"
if [ ! -s "$WORK/preflight.sh" ]; then
  echo "FATAL: WRITE-PREFLIGHT markers missing or empty in $TARGET" >&2; exit 2
fi
for fn in _ocwp_can_write _ocwp_scan_removable _ocwp_print_tree_block oc_remove_tree_guarded oc_assert_write_preflight; do
  if grep -q "^${fn}() {" "$WORK/preflight.sh"; then
    ok "(0) $fn extracted from update-skills.sh"
  else
    echo "FATAL: $fn missing from the extracted WRITE-PREFLIGHT block" >&2; exit 2
  fi
done

hdr "(1) STATIC: no bare skill-tree rm -rf survives, and the guard is wired"
# A bare removal of any of the three trees the updater replaces is the defect.
# Comment lines legitimately quote the old code, so only executable lines count.
NAKED="$(grep -nE '^[[:space:]]*rm -rf "\$SKILLS_DIR/' "$TARGET" || true)"
if [ -z "$NAKED" ]; then
  ok "(1) no executable bare rm -rf of a \$SKILLS_DIR tree remains"
else
  bad "(1) a bare rm -rf of a \$SKILLS_DIR tree survives: $NAKED"
fi
for call in \
  'oc_remove_tree_guarded "$SKILLS_DIR/$SKILL_NAME" "skill"' \
  'oc_remove_tree_guarded "$SKILLS_DIR/universal-sops" "SOP tree"' \
  'oc_remove_tree_guarded "$SKILLS_DIR/32-command-center-setup" "skill"'
do
  if grep -qF "$call" "$TARGET"; then
    ok "(1) wired: $call"
  else
    bad "(1) NOT wired: $call"
  fi
done
# The pre-flight must itself scan the skill trees, or nothing is caught up front.
if awk '/^oc_assert_write_preflight\(\) \{/{p=1} p&&/_ocwp_scan_removable/{found=1} p&&/^\}/{p=0} END{exit !found}' "$TARGET"; then
  ok "(1) oc_assert_write_preflight scans the skill trees for removability"
else
  bad "(1) oc_assert_write_preflight does NOT scan the skill trees"
fi

hdr "(1b) STATIC: the updater writes no python bytecode"
if grep -q '^export PYTHONDONTWRITEBYTECODE=1$' "$TARGET"; then
  ok "(1b) update-skills.sh exports PYTHONDONTWRITEBYTECODE=1"
else
  bad "(1b) update-skills.sh exports PYTHONDONTWRITEBYTECODE=1"
fi
EXPORT_LINE="$(grep -n '^export PYTHONDONTWRITEBYTECODE=1$' "$TARGET" | head -1 | cut -d: -f1)"
# "runs python" means an actual invocation, not the word appearing in prose.
FIRST_PY="$(grep -nE '(^|[^[:alnum:]_])python3? ' "$TARGET" | grep -vE '^\s*[0-9]+:\s*#' | head -1 | cut -d: -f1)"
if [ -n "$EXPORT_LINE" ] && [ -n "$FIRST_PY" ] && [ "$EXPORT_LINE" -lt "$FIRST_PY" ]; then
  ok "(1b) the export precedes the first python invocation (line $EXPORT_LINE < $FIRST_PY)"
else
  bad "(1b) the export must precede the first python invocation (export=$EXPORT_LINE python=$FIRST_PY)"
fi
if [ -f "$LOOPACT" ]; then
  if grep -q '^export PYTHONDONTWRITEBYTECODE=1$' "$LOOPACT" \
     && grep -qF 'PYTHONDONTWRITEBYTECODE=1 bash "$_inst"' "$LOOPACT"; then
    ok "(1b) activate-loop-protection.sh exports it AND restates it on the installer call"
  else
    bad "(1b) activate-loop-protection.sh must export it and restate it on the installer call"
  fi
else
  bad "(1b) $LOOPACT not found"
fi

# shellcheck disable=SC1090
. "$WORK/preflight.sh"
_OCWP_ME="$(id -un 2>/dev/null || echo unknown)"
_OCWP_ME_UID="$(id -u)"
_OCWP_RUN_OWNER="$(id -un):$(id -gn)"
_OCWP_CONTAINER="<slug>-openclaw-1"

hdr "(2) CONTROL FIRST: a fully removable tree scans clean and is really removed"
GOOD="$WORK/good/23-fixture"; make_skill "$GOOD"
GOOD_N="$(count_files "$GOOD")"
if _ocwp_scan_removable "$GOOD"; then
  ok "(2) CONTROL: a normal skill tree scans REMOVABLE (count=$_OCWP_BLOCKED_COUNT)"
else
  bad "(2) CONTROL: a normal skill tree must scan removable (blocked=$_OCWP_BLOCKED_LIST)"
fi
if [ "$GOOD_N" -gt 5 ]; then
  ok "(2) CONTROL: the fixture really has content ($GOOD_N paths)"
else
  bad "(2) CONTROL: the fixture is empty, so nothing below proves anything"
fi
( oc_remove_tree_guarded "$GOOD" "skill" ) >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 0 ] && [ ! -e "$GOOD" ]; then
  ok "(2) CONTROL: oc_remove_tree_guarded removed it and returned 0"
else
  bad "(2) CONTROL: oc_remove_tree_guarded must remove a removable tree (rc=$RC, exists=$([ -e "$GOOD" ] && echo yes || echo no))"
fi

if [ "$AM_ROOT" = "1" ]; then
  hdr "(3-5) blocked-tree cases"
  skip "(3-5) running as uid 0, which bypasses every DAC check: a 0555 directory is writable to root, so no block can be reproduced"
else
  hdr "(3) FIXTURE CONTROL: a bare rm -rf really does fail AND gut the tree"
  # Without this, cases (4) and (5) could pass against a fixture that never
  # reproduced the defect in the first place.
  REPRO="$WORK/repro/23-fixture"; make_skill "$REPRO"
  chmod 0555 "$REPRO/scripts/__pycache__"
  REPRO_N="$(count_files "$REPRO")"
  rm -rf "$REPRO" 2>/dev/null; RM_RC=$?
  REPRO_AFTER="$(count_files "$REPRO")"
  if [ "$RM_RC" -ne 0 ]; then
    ok "(3) a bare rm -rf on the fixture FAILS (rc=$RM_RC), which is what set -e turned into a silent death"
  else
    bad "(3) a bare rm -rf on the fixture must fail, or the fixture does not reproduce the defect"
  fi
  if [ "$REPRO_AFTER" -lt "$REPRO_N" ] && [ "$REPRO_AFTER" -gt 0 ]; then
    ok "(3) and it GUTS the tree: $REPRO_N paths before, $REPRO_AFTER after"
  else
    bad "(3) the bare rm -rf must leave a gutted tree ($REPRO_N -> $REPRO_AFTER)"
  fi
  chmod -R u+rwX "$WORK/repro" 2>/dev/null

  hdr "(4) the scan catches it, and the guard refuses with the tree UNTOUCHED"
  # A NON-bytecode directory: an unremovable __pycache__ is self-healed, see (6).
  BLK="$WORK/blocked/23-fixture"; make_skill "$BLK"
  chmod 0555 "$BLK/references"
  BLK_N="$(count_files "$BLK")"
  if _ocwp_scan_removable "$BLK"; then
    bad "(4) the scan must report the tree as NOT removable"
  else
    ok "(4) the scan reports the tree as NOT removable (count=$_OCWP_BLOCKED_COUNT)"
  fi
  case "$_OCWP_BLOCKED_LIST" in
    *"$BLK/references"*) ok "(4) the scan names the exact blocking directory" ;;
    *) bad "(4) the scan must name $BLK/references (got: $_OCWP_BLOCKED_LIST)" ;;
  esac

  ( oc_remove_tree_guarded "$BLK" "skill" ) > "$WORK/blk.out" 2>&1; BLK_RC=$?
  BLK_AFTER="$(count_files "$BLK")"
  if [ "$BLK_RC" -eq 1 ]; then
    ok "(4) the guard exits 1"
  else
    bad "(4) the guard must exit 1 (got rc=$BLK_RC)"
  fi
  if [ "$BLK_AFTER" = "$BLK_N" ]; then
    ok "(4) THE TREE IS UNTOUCHED: $BLK_N paths before, $BLK_AFTER after"
  else
    bad "(4) the tree must be untouched ($BLK_N -> $BLK_AFTER)"
  fi
  if [ "$(grep -cF 'PERMISSION BLOCK:' "$WORK/blk.out")" -eq 1 ]; then
    ok "(4) exactly ONE PERMISSION BLOCK line, not a wall of them"
  else
    bad "(4) exactly ONE PERMISSION BLOCK line (got $(grep -cF 'PERMISSION BLOCK:' "$WORK/blk.out"))"
  fi
  if grep -qF "PERMISSION BLOCK: $BLK/references is owned by " "$WORK/blk.out" \
     && grep -qF "but the updater runs as $_OCWP_ME" "$WORK/blk.out" \
     && grep -qF "chown -R $_OCWP_RUN_OWNER $BLK" "$WORK/blk.out"; then
    ok "(4) the line carries path + owner + running user + a recursive chown remedy"
  else
    bad "(4) the PERMISSION BLOCK line is incomplete (got: $(cat "$WORK/blk.out"))"
  fi
  if grep -q 'BEFORE ANYTHING WAS DELETED' "$WORK/blk.out"; then
    ok "(4) the refusal states plainly that nothing was deleted"
  else
    bad "(4) the refusal must state that nothing was deleted"
  fi
  chmod -R u+rwX "$WORK/blocked" 2>/dev/null

  hdr "(5) the WRITE PRE-FLIGHT refuses the whole run up front"
  # oc_assert_write_preflight reaches one function defined outside the
  # extracted block. Stub it to its "unresolved" answer, which the pre-flight
  # already handles by skipping the workspace probes, so what is under test
  # here is the skill-tree scan and nothing else.
  run_preflight() {
    local home="$1"
    (
      # shellcheck disable=SC1090
      . "$WORK/preflight.sh"
      oc_resolve_workspace_announced() { return 1; }
      HOME="$home"
      SKILLS_DIR="$home/.openclaw/skills"
      oc_assert_write_preflight
    ) > "$WORK/pf.out" 2>&1
  }
  make_home() {
    local home="$1"
    mkdir -p "$home/.openclaw/skills"
    printf '# agents\n' > "$home/.openclaw/AGENTS.md"
    make_skill "$home/.openclaw/skills/23-fixture"
    make_skill "$home/.openclaw/skills/shared-utils"
  }

  # --- CONTROL FIRST: an all-removable box must PASS the pre-flight.
  PF_OK="$WORK/home-ok"; make_home "$PF_OK"
  run_preflight "$PF_OK"; PF_OK_RC=$?
  if [ "$PF_OK_RC" -eq 0 ]; then
    ok "(5) CONTROL: a box with removable skill trees passes the pre-flight"
  else
    bad "(5) CONTROL: a removable box must pass (rc=$PF_OK_RC, out: $(cat "$WORK/pf.out"))"
  fi
  if grep -qF 'every installed skill tree can be removed and replaced' "$WORK/pf.out"; then
    ok "(5) CONTROL: the pre-flight says so explicitly"
  else
    bad "(5) CONTROL: the pre-flight must announce the skill-tree result"
  fi
  if grep -qF 'PERMISSION BLOCK' "$WORK/pf.out"; then
    bad "(5) CONTROL: a healthy box must print NO permission line"
  else
    ok "(5) CONTROL: a healthy box prints no permission line"
  fi

  # --- and now the blocked box.
  PF_BAD="$WORK/home-bad"; make_home "$PF_BAD"
  chmod 0555 "$PF_BAD/.openclaw/skills/23-fixture/references"
  PF_N="$(count_files "$PF_BAD/.openclaw/skills/23-fixture")"
  run_preflight "$PF_BAD"; PF_BAD_RC=$?
  PF_AFTER="$(count_files "$PF_BAD/.openclaw/skills/23-fixture")"
  if [ "$PF_BAD_RC" -eq 1 ]; then
    ok "(5) a blocked skill tree makes the pre-flight exit 1"
  else
    bad "(5) a blocked skill tree must make the pre-flight exit 1 (got rc=$PF_BAD_RC)"
  fi
  if [ "$PF_AFTER" = "$PF_N" ]; then
    ok "(5) THE TREE IS UNTOUCHED by the pre-flight: $PF_N paths before, $PF_AFTER after"
  else
    bad "(5) the pre-flight must not touch the tree ($PF_N -> $PF_AFTER)"
  fi
  if grep -qF "PERMISSION BLOCK: $PF_BAD/.openclaw/skills/23-fixture/references" "$WORK/pf.out"; then
    ok "(5) it names the exact blocking directory, up front"
  else
    bad "(5) it must name the blocking directory (got: $(cat "$WORK/pf.out"))"
  fi
  if grep -qF "chown -R $_OCWP_RUN_OWNER $PF_BAD/.openclaw/skills/23-fixture" "$WORK/pf.out"; then
    ok "(5) the remedy chowns the whole skill tree, not just the one directory"
  else
    bad "(5) the remedy must be a recursive chown of the skill tree"
  fi
  if grep -qF 'UPDATE REFUSED BEFORE ANY CONTENT WAS TOUCHED.' "$WORK/pf.out"; then
    ok "(5) it refuses through the existing pre-flight banner, before any content step"
  else
    bad "(5) it must refuse through the existing pre-flight banner"
  fi
  if [ "$(grep -cF 'PERMISSION BLOCK:' "$WORK/pf.out")" -le 10 ]; then
    ok "(5) the report is capped at 10 PERMISSION BLOCK lines"
  else
    bad "(5) the report must be capped at 10 lines"
  fi
  chmod -R u+rwX "$WORK/home-bad" 2>/dev/null

  hdr "(6) an unremovable __pycache__ is SELF-HEALED, never a refusal"
  # 2026-09-29: pm2 ran as root on a Hostinger box, the Command Center ran
  # python skills as root, and every later update refused on the root-owned
  # __pycache__ it left. The same 0555 shape stands in for root ownership.
  PY="$WORK/pyc/23-fixture"; make_skill "$PY"
  chmod 0555 "$PY/scripts/__pycache__"
  if _ocwp_scan_removable "$PY" && [ "$_OCWP_BYTECODE_COUNT" -eq 1 ]; then
    ok "(6) the scan passes and counts the cache as bytecode, not a block"
  else
    bad "(6) the scan must pass with one bytecode cache (blocked=$_OCWP_BLOCKED_COUNT bytecode=${_OCWP_BYTECODE_COUNT:-unset})"
  fi
  ( oc_remove_tree_guarded "$PY" "skill" ) > "$WORK/py.out" 2>&1; PY_RC=$?
  LEFT="$(find "$PY" ! -type d | sed "s|^$PY/||" | sort | tr '\n' ' ')"
  if [ "$PY_RC" -eq 0 ] && [ "$LEFT" = "scripts/__pycache__/tool.cpython-311.pyc " ]; then
    ok "(6) the removal returns 0 and leaves ONLY the cache behind"
  else
    bad "(6) removal must return 0 leaving only the cache (rc=$PY_RC left=$LEFT out: $(cat "$WORK/py.out"))"
  fi
  if grep -qF "SELF-HEALED: left 1 python bytecode cache dir(s) in $PY" "$WORK/py.out"; then
    ok "(6) it says what it left and why"
  else
    bad "(6) it must print the SELF-HEALED line (got: $(cat "$WORK/py.out"))"
  fi
  SRC="$WORK/pyc-src/23-fixture"; make_skill "$SRC"; rm -rf "$SRC/scripts/__pycache__"
  printf 'x = 2\n' > "$SRC/scripts/tool.py"
  if cp -r "$SRC" "$WORK/pyc/" 2>/dev/null && [ "$(cat "$PY/scripts/tool.py")" = "x = 2" ] && [ -f "$PY/SKILL.md" ]; then
    ok "(6) the release copy merges into what is left"
  else
    bad "(6) the release copy must merge into what is left"
  fi
  PF_PY="$WORK/home-pyc"; make_home "$PF_PY"
  chmod 0555 "$PF_PY/.openclaw/skills/23-fixture/scripts/__pycache__"
  run_preflight "$PF_PY"; PF_PY_RC=$?
  if [ "$PF_PY_RC" -eq 0 ] && grep -qF 'SELF-HEAL: 1 python bytecode cache dir(s)' "$WORK/pf.out" \
     && ! grep -qF 'PERMISSION BLOCK' "$WORK/pf.out"; then
    ok "(6) the pre-flight passes, with a SELF-HEAL line and no PERMISSION BLOCK"
  else
    bad "(6) the pre-flight must pass on a bytecode-only block (rc=$PF_PY_RC, out: $(cat "$WORK/pf.out"))"
  fi
  chmod -R u+rwX "$WORK/pyc" "$WORK/home-pyc" 2>/dev/null
fi

printf '\nRESULT: PASS=%s FAIL=%s SKIP=%s\n' "$PASS" "$FAIL" "$SKIP"
if [ "$AM_ROOT" = "1" ] && [ -n "${CI:-}" ]; then
  echo "FAIL: this guard cannot be proven as uid 0 (root bypasses every permission check)." >&2
  echo "      Run the CI job as a non-root user so cases (3), (4) and (5) actually execute." >&2
  exit 1
fi
[ "$FAIL" -eq 0 ] || exit 1
