#!/usr/bin/env bash
# tests/unit/bounded-child-deadline.test.sh
#
# Proves BOUNDED-CHILD-V1 in update-skills.sh.
#
# The property under test is the NEGATIVE control: a child that deliberately
# hangs MUST be killed at the deadline, its descendants MUST die with it, and
# the call site MUST be able to tell a timeout (124) apart from a pass (0) and
# from an ordinary failure. A runner that swallowed the timeout into rc 0 would
# mark a hung skill verified and the whole point of the change would be gone.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/update-skills.sh"
PASS=0; FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok()  { PASS=$((PASS + 1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

BLK="$TMP/bounded.sh"
awk '/^#=== BEGIN BOUNDED-CHILD-V1 ===$/,/^#=== END BOUNDED-CHILD-V1 ===$/' "$SRC" > "$BLK"
if [ ! -s "$BLK" ]; then
  echo "FAIL: could not extract BOUNDED-CHILD-V1 block from $SRC"; exit 1
fi
bash -n "$BLK" || { echo "FAIL: extracted block is not valid bash"; exit 1; }

# The wrapper must resolve the repo's ONE deadline runner, so pin _SCRIPT_DIR.
_SCRIPT_DIR="$REPO_ROOT"
OC_CONFIG="$TMP/oc"
ONBOARDING_DIR=""
OPENCLAW_ROOT=""
export _SCRIPT_DIR OC_CONFIG ONBOARDING_DIR OPENCLAW_ROOT
mkdir -p "$OC_CONFIG"
# shellcheck source=/dev/null
source "$BLK"

echo "== positive control (a child that passes) =="
rc=0
out="$(oc_bounded_run 5 pass true 2>&1)" || rc=$?
[ "$rc" = "0" ] && ok "passing child returns 0" || bad "passing child returned rc=$rc"

echo "== negative control (a child that hangs MUST be killed) =="
# The child spawns a GRANDCHILD and waits. If only the direct child were killed,
# the grandchild would survive; the helper kills the whole process group.
GRAND_PID_FILE="$TMP/grandchild.pid"
rc=0
start=$(date +%s)
out="$(oc_bounded_run 1 hang \
  bash -c 'sleep 300 & echo $! > "$1"; wait' _ "$GRAND_PID_FILE" 2>&1)" || rc=$?
elapsed=$(( $(date +%s) - start ))

[ "$rc" = "124" ] && ok "hanging child reports rc=124 (timeout, NOT success)" || bad "hanging child returned rc=$rc (expected 124)"
[ "$elapsed" -lt 20 ] && ok "deadline fired in ${elapsed}s, not 300s" || bad "deadline did not fire (${elapsed}s)"

GRAND_PID="$(cat "$GRAND_PID_FILE" 2>/dev/null || true)"
if [ -n "$GRAND_PID" ]; then
  alive=1
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$GRAND_PID" 2>/dev/null || { alive=0; break; }
    sleep 0.3
  done
  [ "$alive" = "0" ] && ok "grandchild (pid $GRAND_PID) was killed with its group" || bad "grandchild $GRAND_PID survived the deadline"
else
  bad "child never started (no grandchild pid recorded)"
fi

# The runner's own receipt is the durable "recorded unverified" evidence.
receipt="$(ls -1 "$OC_CONFIG"/.onboarding-qc-diagnostics/bounded/hang/qc-script-*/status.json 2>/dev/null | head -n1)"
if [ -n "$receipt" ]; then
  grep -q '"status": *"timeout"' "$receipt" && ok "status.json records status=timeout" || bad "status.json does not record timeout: $(cat "$receipt")"
else
  bad "no status.json receipt written for the timed-out child"
fi

echo "== failure is not a timeout =="
rc=0
out="$(oc_bounded_run 10 fail bash -c 'exit 3' 2>&1)" || rc=$?
[ "$rc" = "3" ] && ok "ordinary failure keeps its own rc (3), not 124" || bad "ordinary failure returned rc=$rc"

echo "== caller semantics: a timeout must never be reported as verified =="
rc=0
out="$(oc_bounded_run 1 hang2 bash -c 'sleep 300' 2>&1)" || rc=$?
[ "$rc" = "124" ] && ok "call site can branch on 124 and record UNVERIFIED" || bad "call-site rc was $rc"

echo "== static: all three previously-unbounded children route through the wrapper =="
for marker in 'oc_bounded_run "$_sp_secs" stamp-pin' 'oc_bounded_run "$_vf_secs" verify' 'oc_bounded_run "$_inst_secs" installer'; do
  grep -qF "$marker" "$SRC" && ok "bounded: ${marker%% *} ${marker#oc_bounded_run }" || bad "missing bounded call site: $marker"
done
# And the bare unbounded forms must be gone. The ONLY surviving DIRECT call
# (a line that starts with `bash "$SKILL_INSTALLER"`) is skill 76's, which sits
# behind its own perl alarm on the preceding line.
n_bare="$(grep -cE '^[[:space:]]*bash "\$SKILL_INSTALLER" --idempotent' "$SRC" || true)"
[ "$n_bare" = "1" ] && ok "exactly one direct installer call remains (skill 76)" || bad "expected 1 direct installer call, found $n_bare"
line="$(grep -nE '^[[:space:]]*bash "\$SKILL_INSTALLER" --idempotent' "$SRC" | cut -d: -f1 | head -n1)"
prev="$(sed -n "$((line - 1))p" "$SRC")"
case "$prev" in
  *"perl -e 'alarm shift"*) ok "the remaining direct call sits behind the perl alarm" ;;
  *) bad "a direct installer call is NOT behind a deadline: $prev" ;;
esac

echo
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
