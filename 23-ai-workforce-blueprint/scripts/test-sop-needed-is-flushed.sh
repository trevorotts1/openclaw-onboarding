#!/usr/bin/env bash
# test-sop-needed-is-flushed.sh — CI guard for BU-108.
#
# WHAT IT TESTS:
#   A role that matches no role-library template must leave a machine-readable
#   SOP-NEEDED record on disk, not only in memory, on EVERY exit path.
#
#     1. create_role_workspaces.py --roles-json on a department inside
#        <company>/departments/ writes <company>/SOP-NEEDED.json with
#        open_count == 1.
#     2. post-build-role-workspaces.py, pointed at the same scratch company
#        through the platform variables, augments a second department's role
#        and the same manifest then holds open_count == 2.
#
#   A scratch company is used throughout; nothing outside it is written.
#
# Exit 0 = every check passed; non-zero = at least one check failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CREATE="$SCRIPT_DIR/create_role_workspaces.py"
POSTBUILD="$SCRIPT_DIR/post-build-role-workspaces.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

# Temp on the drive when TMPDIR points there (the room exports it); never /tmp.
WORK="$(mktemp -d "${TMPDIR:-$PWD}/sopneeded.XXXXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

HOME_DIR="$WORK/home"
MASTER="$WORK/master"
COMPANY="$MASTER/zero-human-company/acme"
WIDGETS="$COMPANY/departments/widgets"
GADGETS="$COMPANY/departments/gadgets"
WS="$WORK/ws"
mkdir -p "$HOME_DIR" "$WIDGETS" "$GADGETS" "$WS"
# A CEO that already exists with a how-to.md: post-build then augments it
# without recording a miss, so the only new record is the one this test adds.
mkdir -p "$COMPANY/master-orchestrator"
printf '# Master Orchestrator\n\nExisting how-to; not the subject of this test.\n' \
  > "$COMPANY/master-orchestrator/how-to.md"

open_count() {  # open_count of the manifest, or MISSING
  python3 -B - "$COMPANY/SOP-NEEDED.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    print("MISSING")
else:
    print(json.loads(p.read_text(encoding="utf-8")).get("open_count"))
PY
}

# ── 1. create_role_workspaces.py --roles-json flushes the record ─────────────
ROLES="$WORK/roles.json"
cat > "$ROLES" <<'JSON'
[{"name": "Zyzzyva Compliance Wrangler", "type": "full-time-permanent", "is_ceo": false}]
JSON

env -i HOME="$HOME_DIR" PATH="$PATH" OPENCLAW_PLATFORM=mac \
  MASTER_FILES_DIR="$MASTER" \
  python3 -B "$CREATE" --dept-path "$WIDGETS" --roles-json "$ROLES" \
    --workspace-root "$WS" >"$WORK/create.log" 2>&1
RC=$?
if [ "$RC" -eq 0 ]; then ok "create_role_workspaces.py exited 0"; else
  bad "create_role_workspaces.py exited $RC (log: $WORK/create.log)"; fi
OC="$(open_count)"
if [ "$OC" = "1" ]; then ok "manifest written with open_count == 1"; else
  bad "expected open_count == 1, got '$OC'"; fi
if grep -q "SOP-NEEDED" "$WORK/create.log"; then
  ok "the library miss is named in the run log"
else
  bad "no SOP-NEEDED line in the create run log"
fi

# ── 2. post-build-role-workspaces.py flushes its own records ────────────────
# A role folder with no library template: augmentation records the miss.
mkdir -p "$GADGETS/Vexing Gadget Overseer"
env -i HOME="$HOME_DIR" PATH="$PATH" OPENCLAW_PLATFORM=mac \
  MASTER_FILES_DIR="$MASTER" \
  python3 -B "$POSTBUILD" >"$WORK/post.log" 2>&1
RC=$?
if [ "$RC" -eq 0 ]; then ok "post-build-role-workspaces.py exited 0"; else
  bad "post-build-role-workspaces.py exited $RC (log: $WORK/post.log)"; fi
OC="$(open_count)"
if [ "$OC" = "2" ]; then ok "after post-build the manifest holds open_count == 2"; else
  bad "expected open_count == 2, got '$OC'"; fi

# ── housekeeping: nothing outside the scratch folder ────────────────────────
if [ -z "$(ls -A "$HOME_DIR" 2>/dev/null)" ]; then
  ok "HOME stayed empty (no stray install files)"
else
  bad "HOME is not empty: $(ls -A "$HOME_DIR" | head -3 | tr '\n' ' ')"
fi

echo ""
echo "=========================================="
echo "SOP-NEEDED flush guard: PASS=$PASS FAIL=$FAIL"
echo "=========================================="
[ "$FAIL" -eq 0 ]
exit $?
