#!/usr/bin/env bash
# ============================================================================
# updater-write-preflight-permission-block.test.sh
#
# THE DEFECT THIS LOCKS (measured 2026-09-17, nine Hostinger VPS boxes).
# Inside each openclaw container, /data/.openclaw/workspace/AGENTS.md was
# root:root 0644 while /data/.openclaw and /data/.openclaw/workspace are
# node:node 0700 and the updater runs as uid 1000 (node). AGENTS.md was
# therefore READABLE and NOT WRITABLE. Every read-side gate passed, the content
# gate PASSED, and then the CORE_UPDATES merge, hundreds of lines into an
# embedded python program, opened AGENTS.md for append and died with
#   PermissionError: [Errno 13] Permission denied: .../workspace/AGENTS.md
# update-skills.sh exited 1 halfway through, the version stamp was WITHHELD,
# and the operator got a raw traceback in the middle of a very long log with a
# green content gate printed above it. Nine boxes sat STALE.
#
# THE CONTRACT UNDER TEST
#   1. update-skills.sh carries the write pre-flight and CALLS it from main().
#   2. The pre-flight proves writability with a real write attempt, not `-w`.
#   3. An unwritable path it can repair is repaired and logged FIXED.
#   4. An unwritable path it cannot repair produces ONE PERMISSION BLOCK line
#      naming the owner, the user and the remedy, and blocks the run.
#   5. The CORE_UPDATES embedded python emits that SAME line and exits 1 on a
#      read-only AGENTS.md, with NO traceback.
#   6. KNOWN-GOOD CONTROL: the identical python run against a WRITABLE
#      AGENTS.md merges the block, stamps the sentinel, exits 0 and prints no
#      PERMISSION BLOCK. Without this control a broken extractor would make
#      case 5 pass for the wrong reason.
#
# METHOD. Nothing is reimplemented. The shell block and the python program are
# EXTRACTED VERBATIM from update-skills.sh between markers; if a marker drifts
# or vanishes this suite exits 2 rather than silently testing nothing.
#
# SAFETY. Every case runs inside mktemp -d. No network, no box, no SSH, and
# nothing outside the temp tree is opened for writing.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
TARGET="$REPO/update-skills.sh"

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

# --- verbatim extraction between markers ------------------------------------
extract_block() {
  awk -v b=">>> $1-BEGIN" -v e="<<< $1-END" '
    index($0, b) { p=1; next }
    index($0, e) { p=0 }
    p { print }
  ' "$TARGET"
}

hdr "(0) the markers still exist, so this suite cannot silently test nothing"
extract_block WRITE-PREFLIGHT > "$WORK/preflight.sh"
extract_block CORE-UPDATES-PY > "$WORK/core_updates.py"
if [ -s "$WORK/preflight.sh" ] && grep -q 'oc_assert_write_preflight()' "$WORK/preflight.sh"; then
  ok "(0) WRITE-PREFLIGHT block extracted from update-skills.sh"
else
  echo "FATAL: WRITE-PREFLIGHT markers missing or empty in $TARGET" >&2
  exit 2
fi
if [ -s "$WORK/core_updates.py" ] && grep -q '_oc_write_failed' "$WORK/core_updates.py"; then
  ok "(0) CORE-UPDATES-PY block extracted from update-skills.sh"
else
  echo "FATAL: CORE-UPDATES-PY markers missing or empty in $TARGET" >&2
  exit 2
fi

hdr "(1) STATIC: the pre-flight is WIRED, and the python writes are guarded"
if grep -q '^  oc_assert_write_preflight$' "$TARGET"; then
  ok "(1) main() calls oc_assert_write_preflight"
else
  bad "(1) main() calls oc_assert_write_preflight"
fi
# The call must precede the CORE_UPDATES merge, or it guards nothing.
CALL_LINE="$(grep -n '^  oc_assert_write_preflight$' "$TARGET" | head -1 | cut -d: -f1)"
MERGE_LINE="$(grep -n 'CORE-UPDATES-PY-BEGIN' "$TARGET" | head -1 | cut -d: -f1)"
if [ -n "$CALL_LINE" ] && [ -n "$MERGE_LINE" ] && [ "$CALL_LINE" -lt "$MERGE_LINE" ]; then
  ok "(1) the pre-flight call comes BEFORE the CORE_UPDATES merge"
else
  bad "(1) the pre-flight call comes BEFORE the CORE_UPDATES merge (call=$CALL_LINE merge=$MERGE_LINE)"
fi
# Neither AGENTS.md write may sit outside a try/except any more.
if python3 - "$WORK/core_updates.py" <<'PY'
import ast, sys
tree = ast.parse(open(sys.argv[1], encoding='utf-8').read())
guarded = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Try):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and getattr(sub.func, 'id', '') == 'open':
                if len(sub.args) > 1 and isinstance(sub.args[1], ast.Constant):
                    guarded.add((sub.args[1].value, sub.lineno))
naked = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'open':
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            if node.args[1].value in ('a', 'w') and (node.args[1].value, node.lineno) not in guarded:
                naked.append(node.lineno)
if naked:
    print('UNGUARDED write-mode open() at lines: ' + repr(naked))
    sys.exit(1)
sys.exit(0)
PY
then
  ok "(1) every write-mode open() in the CORE_UPDATES program sits inside a try"
else
  bad "(1) every write-mode open() in the CORE_UPDATES program sits inside a try"
fi

hdr "(2) the write probe is a REAL write attempt, not a -w guess"
# shellcheck disable=SC1090
. "$WORK/preflight.sh"

F_OK="$WORK/writable.md"; printf 'keep me\n' > "$F_OK"
BEFORE="$(cksum < "$F_OK")"
if _ocwp_can_write "$F_OK"; then ok "(2) a writable file probes writable"; else bad "(2) a writable file probes writable"; fi
if [ "$(cksum < "$F_OK")" = "$BEFORE" ]; then
  ok "(2) the probe changed no content (append of zero bytes, never a truncate)"
else
  bad "(2) the probe changed no content"
fi

D_OK="$WORK/dir-ok"; mkdir -p "$D_OK"
if _ocwp_can_write "$D_OK"; then ok "(2) a writable directory probes writable"; else bad "(2) a writable directory probes writable"; fi
if [ -z "$(ls -A "$D_OK")" ]; then ok "(2) the directory probe removed its own probe file"; else bad "(2) the directory probe left a file behind"; fi

MISSING="$WORK/dir-ok/not-yet.md"
if _ocwp_can_write "$MISSING"; then
  ok "(2) a not-yet-created file defers to its writable parent"
else
  bad "(2) a not-yet-created file defers to its writable parent"
fi

if [ "$AM_ROOT" = "1" ]; then
  skip "(2) mode-based unwritable cases: running as uid 0, which bypasses every DAC check"
else
  F_RO="$WORK/readonly.md"; printf 'x\n' > "$F_RO"; chmod 0444 "$F_RO"
  if _ocwp_can_write "$F_RO"; then bad "(2) a 0444 file must probe UNWRITABLE"; else ok "(2) a 0444 file probes unwritable"; fi
  D_RO="$WORK/dir-ro"; mkdir -p "$D_RO"; chmod 0555 "$D_RO"
  if _ocwp_can_write "$D_RO"; then bad "(2) a 0555 directory must probe UNWRITABLE"; else ok "(2) a 0555 directory probes unwritable"; fi
  chmod 0755 "$D_RO"
fi

hdr "(3) SELF-HEAL: a path we own but cannot write is repaired and logged FIXED"
if [ "$AM_ROOT" = "1" ]; then
  skip "(3) self-heal: running as uid 0, the probe never fails so no heal is exercised"
else
  _OCWP_ME="$(id -un)"; _OCWP_ME_UID="$(id -u)"
  _OCWP_RUN_OWNER="$(id -un):$(id -gn)"; _OCWP_CONTAINER="<container>"
  F_HEAL="$WORK/heal.md"; printf 'y\n' > "$F_HEAL"; chmod 0444 "$F_HEAL"
  HEAL_OUT="$(_ocwp_check_one "$F_HEAL" hard 2>&1)"; HEAL_RC=$?
  if [ "$HEAL_RC" -eq 0 ]; then ok "(3) a repairable path does not block the run"; else bad "(3) a repairable path must not block the run (rc=$HEAL_RC)"; fi
  case "$HEAL_OUT" in
    *"FIXED: $F_HEAL ownership"*) ok "(3) the repair is announced as FIXED" ;;
    *) bad "(3) the repair is announced as FIXED (got: $HEAL_OUT)" ;;
  esac
  if _ocwp_can_write "$F_HEAL"; then ok "(3) the path is genuinely writable after the repair"; else bad "(3) the path is genuinely writable after the repair"; fi
fi

hdr "(4) BLOCK: an unrepairable path yields ONE actionable line and blocks"
# Deterministic on any host, root or not: the probe and the owner lookup are
# stubbed so the DECISION LOGIC is what is under test, not the runner's uid.
(
  # shellcheck disable=SC1090
  . "$WORK/preflight.sh"
  _ocwp_can_write()  { return 1; }
  _ocwp_owner()      { printf '%s' "root:root"; }
  _ocwp_owner_uid()  { printf '%s' "0"; }
  _OCWP_ME="node"; _OCWP_ME_UID="1000"
  _OCWP_RUN_OWNER="node:node"; _OCWP_CONTAINER="<slug>-openclaw-1"
  OUT="$(_ocwp_check_one /data/.openclaw/workspace/AGENTS.md hard 2>&1)"; RC=$?
  printf '%s\n' "$RC" > "$WORK/block.rc"
  printf '%s\n' "$OUT" > "$WORK/block.out"

  OUT2="$(_ocwp_check_one /data/.openclaw/scripts soft 2>&1)"; RC2=$?
  printf '%s\n' "$RC2" > "$WORK/soft.rc"
  printf '%s\n' "$OUT2" > "$WORK/soft.out"
)
if [ "$(cat "$WORK/block.rc")" = "1" ]; then ok "(4) a hard path that cannot be repaired blocks (rc=1)"; else bad "(4) a hard path must block (rc=$(cat "$WORK/block.rc"))"; fi
EXPECT='PERMISSION BLOCK: /data/.openclaw/workspace/AGENTS.md is owned by root:root but the updater runs as node; on a Docker box run: docker exec <slug>-openclaw-1 chown node:node /data/.openclaw/workspace/AGENTS.md'
if grep -qF "$EXPECT" "$WORK/block.out"; then
  ok "(4) the exact PERMISSION BLOCK line is printed, owner + user + remedy on one line"
else
  bad "(4) the exact PERMISSION BLOCK line is printed (got: $(cat "$WORK/block.out"))"
fi
if [ "$(grep -cF 'PERMISSION BLOCK:' "$WORK/block.out")" -eq 1 ]; then
  ok "(4) exactly ONE PERMISSION BLOCK line, not a wall of them"
else
  bad "(4) exactly ONE PERMISSION BLOCK line"
fi
if [ "$(cat "$WORK/soft.rc")" = "0" ] && grep -qF 'PERMISSION DEFERRED:' "$WORK/soft.out"; then
  ok "(4) a soft path is reported as DEFERRED and does NOT block the version stamp"
else
  bad "(4) a soft path is reported as DEFERRED and does NOT block (rc=$(cat "$WORK/soft.rc"))"
fi

hdr "(5) CORE_UPDATES python: a read-only AGENTS.md is one line, never a traceback"
run_core_updates() {
  # $1 = box dir. Returns the program's rc; stdout+stderr land in $1/out.txt
  local box="$1"
  python3 "$WORK/core_updates.py" \
    "$box/CORE_UPDATES.md" "$box/AGENTS.md" "$box/TOOLS.md" "$box/MEMORY.md" \
    "$box/SOUL.md" "$box/IDENTITY.md" "$box/USER.md" \
    '<!-- skill:99-test-skill:core-update-applied -->' '99-test-skill' \
    '0' "$box/master-files" > "$box/out.txt" 2>&1
}
make_box() {
  local box="$1"; mkdir -p "$box"
  printf '## AGENTS.md - UPDATE REQUIRED\n\nA core update block body.\n' > "$box/CORE_UPDATES.md"
  local f
  for f in AGENTS.md TOOLS.md MEMORY.md SOUL.md IDENTITY.md USER.md; do
    printf '# %s\n\nexisting content\n' "$f" > "$box/$f"
  done
}

# --- KNOWN-GOOD CONTROL FIRST. If this fails, the extractor is broken and the
# --- negative case below would pass for the wrong reason.
CTRL="$WORK/box-control"; make_box "$CTRL"
run_core_updates "$CTRL"; CTRL_RC=$?
if [ "$CTRL_RC" -eq 0 ]; then ok "(5) CONTROL: a writable AGENTS.md exits 0"; else bad "(5) CONTROL: a writable AGENTS.md exits 0 (rc=$CTRL_RC, out: $(cat "$CTRL/out.txt"))"; fi
if grep -qF '<!-- BEGIN skill:99-test-skill:agents -->' "$CTRL/AGENTS.md"; then
  ok "(5) CONTROL: the block really was merged (the program does real work)"
else
  bad "(5) CONTROL: the block really was merged"
fi
if grep -qF '<!-- skill:99-test-skill:core-update-applied -->' "$CTRL/AGENTS.md"; then
  ok "(5) CONTROL: the sentinel really was stamped"
else
  bad "(5) CONTROL: the sentinel really was stamped"
fi
if grep -qF 'PERMISSION BLOCK' "$CTRL/out.txt"; then
  bad "(5) CONTROL: a healthy run must print NO permission line"
else
  ok "(5) CONTROL: a healthy run prints no permission line"
fi

if [ "$AM_ROOT" = "1" ]; then
  skip "(5) read-only AGENTS.md: running as uid 0, which can write a 0444 file"
else
  RO="$WORK/box-readonly"; make_box "$RO"; chmod 0444 "$RO/AGENTS.md"
  run_core_updates "$RO"; RO_RC=$?
  if [ "$RO_RC" -eq 1 ]; then ok "(5) a read-only AGENTS.md exits 1"; else bad "(5) a read-only AGENTS.md exits 1 (got rc=$RO_RC)"; fi
  if grep -qF 'PERMISSION BLOCK:' "$RO/out.txt"; then
    ok "(5) the PERMISSION BLOCK line is printed"
  else
    bad "(5) the PERMISSION BLOCK line is printed (got: $(cat "$RO/out.txt"))"
  fi
  if grep -qF "$RO/AGENTS.md" "$RO/out.txt"; then
    ok "(5) the line names the exact unwritable path"
  else
    bad "(5) the line names the exact unwritable path"
  fi
  if grep -q 'Traceback (most recent call last)' "$RO/out.txt"; then
    bad "(5) NO python traceback is printed"
  else
    ok "(5) no python traceback is printed"
  fi
  if grep -q "PermissionError: \[Errno 13\]" "$RO/out.txt"; then
    bad "(5) the raw PermissionError is not dumped at the operator"
  else
    ok "(5) the raw PermissionError is not dumped at the operator"
  fi
  chmod 0644 "$RO/AGENTS.md"
fi

printf '\nRESULT: PASS=%s FAIL=%s SKIP=%s\n' "$PASS" "$FAIL" "$SKIP"
if [ "$AM_ROOT" = "1" ] && [ -n "${CI:-}" ]; then
  echo "FAIL: this guard cannot be proven as uid 0 (root bypasses every permission check)." >&2
  echo "      Run the CI job as a non-root user so cases (2), (3) and (5) actually execute." >&2
  exit 1
fi
[ "$FAIL" -eq 0 ] || exit 1
