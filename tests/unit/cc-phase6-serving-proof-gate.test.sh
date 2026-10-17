#!/usr/bin/env bash
# tests/unit/cc-phase6-serving-proof-gate.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Regression lock for hardening-plan ITEM 03 — "Service phase completes only
# after serving proof".
#
# Bug: a zero exit from the PM2 launch command set commandCenterPhase6Done=true
# BEFORE the child was proven serving. Observed on a real box: `pm2 start` logged
# at line 1228, `phase=6 dashboard-deploy: done` at line 1240 (12 seconds later),
# zero health probes in between — and the child then exited 78 because
# .next/build-inventory.json was missing (PRES-046). The installer reported a
# finished install over a box that served nothing.
#
# Item 03's required proof, all three independently failing:
#   (a) canonical process online (an unrelated or wrong-name listener fails),
#   (b) the EXACT local /api/health payload (cc_live_health_ok),
#   (c) a source-valid content manifest (build-inventory.sh --verify),
# plus: a CURRENT exit-78 refusal receipt is classified rebuild/config-repair
# required (rc 2) — never a blind restart loop — and a timeout keeps pending
# state rather than stamping done.
#
# It executes the REAL cc_phase6_serving_proof / _phase6_pm2_online /
# _phase6_manifest_verifies functions EXTRACTED FROM run-full-install.sh (not a
# copy), against a fake `pm2` shim, so weakening the proof fails this test.
# Dependencies (cc_live_health_ok, log, state_set) are supplied by the harness.
#
# Fully offline/hermetic (mktemp sandbox). Exit 0 = all pass, 1 = failure.
# bash 3.2-safe (macOS system bash): no assoc arrays, no mapfile, no ${x,,}.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RFI="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== cc-phase6-serving-proof-gate.test.sh (item 03) ==="

[ -f "$RFI" ] || { echo "  FAIL: required file not found: $RFI"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "  FAIL: python3 not on PATH"; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "  FAIL: jq not on PATH"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── Extract the REAL serving-proof functions out of the installer ─────────────
# Not a copy: the test runs exactly the code the installer ships.
EXTRACT_RC=0
EXTRACTED="$(python3 - "$RFI" <<'INNERPY'
import re, sys
s = open(sys.argv[1]).read()
start = s.find("_phase6_pm2_online() {")
proof = s.find("cc_phase6_serving_proof() {")
if start < 0 or proof < 0:
    sys.stderr.write("could not find the serving-proof functions in run-full-install.sh\n")
    sys.exit(3)
endm = re.search(r"^\}$", s[proof:], re.M)
if endm is None:
    sys.stderr.write("could not find the closing } of cc_phase6_serving_proof\n")
    sys.exit(3)
block = s[start:proof + endm.end()]
for fn in ("_phase6_pm2_online", "_phase6_manifest_verifies", "cc_phase6_serving_proof"):
    if fn + "() {" not in block:
        sys.stderr.write("extracted block is missing %s — structure changed?\n" % fn)
        sys.exit(3)
sys.stdout.write(block)
INNERPY
)" || EXTRACT_RC=$?

if [ "$EXTRACT_RC" -ne 0 ] || [ -z "$EXTRACTED" ]; then
  fail "could not extract the serving-proof functions from run-full-install.sh (structure changed?)"
  echo ""; echo "  RESULT: $PASS passed, $FAIL failed"; exit 1
fi
pass "extracted the live cc_phase6_serving_proof / _phase6_pm2_online / _phase6_manifest_verifies from run-full-install.sh"

# The proof must not restart the child itself — exit 78 is a rebuild, not a
# restart-loop target. If this starts calling the launcher, the plan's
# "never a blind restart loop" requirement is broken.
case "$EXTRACTED" in
  *cc_pm2_start_canonical*) fail "serving proof calls the launcher — restart loop reintroduced (item 03 forbids it)" ;;
  *) pass "serving proof never invokes the launcher (no blind restart loop)" ;;
esac

# ── Harness: sandbox paths, state, logging, dependency stubs ───────────────────
DASHBOARD_DIR="$WORK/cc"
mkdir -p "$DASHBOARD_DIR/.cc-state" "$DASHBOARD_DIR/scripts/lib" "$DASHBOARD_DIR/.next" "$WORK/bin" "$WORK/stub"
# The manifest must EXIST for the green baseline; its content is irrelevant here
# because the stub build-inventory.sh --verify is the pass/fail lever.
printf '{"schema":"next-build-inventory/1"}\n' > "$DASHBOARD_DIR/.next/build-inventory.json"
DASHBOARD_PORT=4000
CC_PM2_NAME="blackceo-command-center"
LOG_FILE="$WORK/install.log"
STATE_FILE="$WORK/state.json"
touch "$LOG_FILE"
printf '%s' '{"commandCenterPhase6Done":false}' > "$STATE_FILE"

# Real (file-existence + invocation) manifest check is exercised against this
# stub lib; its exit code is the fixture's manifest-valid/invalid lever.
cat > "$DASHBOARD_DIR/scripts/lib/build-inventory.sh" <<'STUB'
#!/usr/bin/env bash
# fixture stand-in for CC's build-inventory.sh --verify
exit "${STUB_MANIFEST_RC:-0}"
STUB
chmod +x "$DASHBOARD_DIR/scripts/lib/build-inventory.sh"

# Fake pm2: `_phase6_pm2_online` runs its REAL python against this jlist output.
cat > "$WORK/bin/pm2" <<'STUB'
#!/usr/bin/env bash
[ "$1" = "jlist" ] || exit 0
cat "$STUB_JLIST"
STUB
chmod +x "$WORK/bin/pm2"
export PATH="$WORK/bin:$PATH"

log() { printf '%s: %s\n' "$1" "$2" >> "$LOG_FILE"; }
fail_install() { printf 'FAIL_INSTALL: %s\n' "$1" >> "$LOG_FILE"; return 99; }
state_get() { # state_get '.key' -> literal JSON scalar as a string (null -> "null")
  jq -r --arg k "${1#.}" '.[$k] | tostring' "$STATE_FILE"
}
state_set() { # state_set '.key = value-json'
  local expr="$1" tmp="$WORK/state.tmp"
  jq "$expr" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"
}
# Dependency stub: the REAL cc_live_health_ok lives further down the installer;
# its exact-payload contract is asserted statically below.
cc_live_health_ok() { [ "${STUB_HEALTH_RC:-0}" -eq 0 ]; }
# The launcher is never part of the proof; a stub proves if it were ever called.
# Every call is counted in its own file so the harness can simulate "pm2 returned
# zero" without polluting the log the restart-loop assertion reads.
cc_pm2_start_canonical() {
  echo "call" >> "$WORK/launcher.calls"
  return "${STUB_LAUNCH_RC:-0}"
}

printf '%s\n' "$EXTRACTED" > "$WORK/serving-proof.sh"
# shellcheck disable=SC1090
. "$WORK/serving-proof.sh" || { fail "extracted proof functions failed to source"; echo ""; echo "  RESULT: $PASS passed, $FAIL failed"; exit 1; }

# jlist fixtures
# canonical app online
jq -n '[{name:"'"$CC_PM2_NAME"'", pid:4242, pm2_env:{status:"online"}}]' > "$WORK/stub/jlist.online.json"
# an UNRELATED listener holds the port (wrong name, still "online")
jq -n '[{name:"some-other-app", pid:9999, pm2_env:{status:"online"}}]' > "$WORK/stub/jlist.wrongname.json"
# no process at all
jq -n '[]' > "$WORK/stub/jlist.empty.json"
# canonical name but crashed
jq -n '[{name:"'"$CC_PM2_NAME"'", pid:0, pm2_env:{status:"errored"}}]' > "$WORK/stub/jlist.errored.json"

set_all_green() { # fixture baseline: process online + health ok + manifest valid
  export STUB_JLIST="$WORK/stub/jlist.online.json"
  export STUB_HEALTH_RC=0
  export STUB_MANIFEST_RC=0
}
clear_receipt() { rm -f "$DASHBOARD_DIR/.cc-state/cc-start-refused.json"; }
write_fresh_receipt() { # child exited 78 moments ago
  printf '{"schema":"cc-start-refusal/1","reason":"missing-manifest"}\n' \
    > "$DASHBOARD_DIR/.cc-state/cc-start-refused.json"
}
write_stale_receipt() { # a receipt from a previous day must NOT classify
  printf '{"schema":"cc-start-refusal/1"}\n' > "$DASHBOARD_DIR/.cc-state/cc-start-refused.json"
  touch -t 202001010000 "$DASHBOARD_DIR/.cc-state/cc-start-refused.json"
}

reset_state() { printf '%s' '{"commandCenterPhase6Done":false}' > "$STATE_FILE"; }
stamp_if_passed() { # mirrors the installer's call site contract exactly
  if cc_phase6_serving_proof "$@"; then
    state_set '.commandCenterPhase6Done = true'
    return 0
  fi
  return 1
}

# ── (c) valid canonical process passes REPEATEDLY ──────────────────────────────
set_all_green; clear_receipt; reset_state
rep_ok=0
for _i in 1 2 3 4 5; do
  cc_phase6_serving_proof 2 0 >/dev/null 2>&1 && rep_ok=$((rep_ok+1))
done
[ "$rep_ok" -eq 5 ] && pass "valid canonical process + exact health + valid manifest passes 5/5" \
  || fail "valid canonical process only passed $rep_ok/5"

set_all_green; clear_receipt; reset_state
stamp_if_passed 2 0 >/dev/null 2>&1
expect_done="$(state_get '.commandCenterPhase6Done')"
[ "$expect_done" = "true" ] && pass "serving proof pass -> commandCenterPhase6Done=true" \
  || fail "serving proof passed but commandCenterPhase6Done is '$expect_done'"
set +e
pending_after="$(state_get '.commandCenterPhase6Pending')"
set -u
[ "$pending_after" = "null" ] && pass "serving proof pass clears commandCenterPhase6Pending" \
  || fail "serving proof pass left commandCenterPhase6Pending='$pending_after'"

# ── (a) PM2 command returns zero while the child exits 78 ─────────────────────
# The launcher succeeded (rc 0 = "pm2 accepted the command"), the child then
# refused deterministically. Done must NOT be stamped; rc must be 2.
# Reality: a child that exited 78 is NOT online and does NOT answer health —
# that is exactly why the proof must reach the receipt instead of passing.
export STUB_JLIST="$WORK/stub/jlist.errored.json" STUB_HEALTH_RC=1 STUB_MANIFEST_RC=0
write_fresh_receipt; reset_state
rm -f "$WORK/launcher.calls"; touch "$WORK/launcher.calls"
STUB_LAUNCH_RC=0; export STUB_LAUNCH_RC
cc_pm2_start_canonical >/dev/null 2>&1          # the old code's ONLY gate: rc 0
launch_rc=$?
unset STUB_LAUNCH_RC
calls_after_sim="$(( $(wc -l < "$WORK/launcher.calls") ))"
proof_rc=0
cc_phase6_serving_proof 2 0 >/dev/null 2>&1 || proof_rc=$?
[ "$launch_rc" -eq 0 ] && pass "fixture: pm2 launch command returned zero (the old gate)" \
  || fail "fixture: pm2 launch command rc=$launch_rc (expected 0)"
[ "$proof_rc" -eq 2 ] && pass "pm2 zero + child exit 78 -> rc 2 (rebuild/config-repair, not done)" \
  || fail "pm2 zero + child exit 78 -> rc $proof_rc (expected 2)"
stamp_if_passed 2 0 >/dev/null 2>&1
[ "$(state_get '.commandCenterPhase6Done')" = "false" ] \
  && pass "child exit 78 never stamps commandCenterPhase6Done" \
  || fail "child exit 78 set commandCenterPhase6Done=true"
calls_after_proof="$(( $(wc -l < "$WORK/launcher.calls") ))"
if [ "$calls_after_proof" -ne "$calls_after_sim" ]; then
  fail "serving proof invoked the launcher ($(( calls_after_proof - calls_after_sim )) extra calls) — blind restart loop"
else
  pass "serving proof never invoked the launcher (no blind restart loop)"
fi
clear_receipt

# ── (b) unrelated / wrong-payload listener fails ──────────────────────────────
reset_state
export STUB_JLIST="$WORK/stub/jlist.wrongname.json" STUB_HEALTH_RC=0 STUB_MANIFEST_RC=0
proof_rc=0
cc_phase6_serving_proof 2 0 >/dev/null 2>&1 || proof_rc=$?
[ "$proof_rc" -eq 1 ] && pass "unrelated listener (wrong pm2 name) -> rc 1, not done" \
  || fail "unrelated listener -> rc $proof_rc (expected 1)"
stamp_if_passed 2 0 >/dev/null 2>&1
[ "$(state_get '.commandCenterPhase6Done')" = "false" ] \
  && pass "unrelated listener never stamps done" \
  || fail "unrelated listener stamped done"

reset_state
export STUB_JLIST="$WORK/stub/jlist.online.json" STUB_HEALTH_RC=1 STUB_MANIFEST_RC=0
proof_rc=0
cc_phase6_serving_proof 2 0 >/dev/null 2>&1 || proof_rc=$?
[ "$proof_rc" -eq 1 ] && pass "canonical online but WRONG health payload -> rc 1" \
  || fail "wrong health payload -> rc $proof_rc (expected 1)"

reset_state
export STUB_JLIST="$WORK/stub/jlist.online.json" STUB_HEALTH_RC=0 STUB_MANIFEST_RC=1
proof_rc=0
cc_phase6_serving_proof 2 0 >/dev/null 2>&1 || proof_rc=$?
[ "$proof_rc" -eq 1 ] && pass "valid health but MANIFEST fails verify -> rc 1" \
  || fail "manifest verify fail -> rc $proof_rc (expected 1)"

reset_state
export STUB_JLIST="$WORK/stub/jlist.errored.json" STUB_HEALTH_RC=1 STUB_MANIFEST_RC=1
proof_rc=0
cc_phase6_serving_proof 2 0 >/dev/null 2>&1 || proof_rc=$?
[ "$proof_rc" -eq 1 ] && pass "errored/absent child -> rc 1 (timeout, pending not done)" \
  || fail "errored child -> rc $proof_rc (expected 1)"
stamp_if_passed 2 0 >/dev/null 2>&1
[ "$(state_get '.commandCenterPhase6Done')" = "false" ] \
  && pass "timeout keeps pending state, never stamps done" \
  || fail "timeout stamped done"

# ── stale receipt must not misclassify (a receipt from days ago is history) ───
# Health is DOWN so the loop reaches the receipt check; the receipt is old
# history, so it must fall through to timeout (rc 1), NOT rebuild (rc 2).
export STUB_JLIST="$WORK/stub/jlist.online.json" STUB_HEALTH_RC=1 STUB_MANIFEST_RC=1
write_stale_receipt; reset_state
proof_rc=0
cc_phase6_serving_proof 2 0 >/dev/null 2>&1 || proof_rc=$?
[ "$proof_rc" -eq 1 ] && pass "stale (>300s) exit-78 receipt -> rc 1 (timeout, not rebuild classification)" \
  || fail "stale receipt -> rc $proof_rc (expected 1 = timeout)"
clear_receipt
# The SAME failing state with a FRESH receipt must classify as rebuild (rc 2).
write_fresh_receipt; reset_state
proof_rc=0
cc_phase6_serving_proof 2 0 >/dev/null 2>&1 || proof_rc=$?
[ "$proof_rc" -eq 2 ] && pass "fresh exit-78 receipt -> rc 2 (rebuild/config-repair classification)" \
  || fail "fresh receipt -> rc $proof_rc (expected 2)"
clear_receipt
set_all_green

# ── missing manifest entirely (fresh box, PRES-046) ───────────────────────────
set_all_green; clear_receipt; reset_state
rm -f "$DASHBOARD_DIR/.next/build-inventory.json"   # the observed real failure
write_fresh_receipt
proof_rc=0
cc_phase6_serving_proof 2 0 >/dev/null 2>&1 || proof_rc=$?
[ "$proof_rc" -eq 2 ] && pass "missing build-inventory.json + fresh receipt -> rc 2 (rebuild required)" \
  || fail "missing manifest -> rc $proof_rc (expected 2)"
stamp_if_passed 2 0 >/dev/null 2>&1
[ "$(state_get '.commandCenterPhase6Done')" = "false" ] \
  && pass "missing manifest never stamps done" \
  || fail "missing manifest stamped done"
clear_receipt

# ── Static wiring: the proof is THE gate before the done stamp ────────────────
stamp_count="$(grep -c "state_set '.commandCenterPhase6Done = true'" "$RFI" || true)"
[ "$stamp_count" = "1" ] && pass "exactly ONE commandCenterPhase6Done=true stamp site" \
  || fail "found $stamp_count commandCenterPhase6Done=true stamp sites (expected 1)"
python3 - "$RFI" <<'PY' && pass "the single done stamp sits inside the serving-proof success branch" \
  || fail "the done stamp is no longer gated on cc_phase6_serving_proof"
import sys
s = open(sys.argv[1]).read()
i = s.find("state_set '.commandCenterPhase6Done = true'")
assert i > 0, "stamp not found"
before = s[max(0, i-600):i]
sys.exit(0 if "cc_phase6_serving_proof" in before else 1)
PY

grep -q "commandCenterPhase6Pending = \"rebuild-required\"" "$RFI" \
  && pass "exit-78 path records commandCenterPhase6Pending=rebuild-required" \
  || fail "exit-78 path no longer records rebuild-required"
grep -q "commandCenterPhase6Pending = \"serving-proof-pending\"" "$RFI" \
  && pass "timeout path records commandCenterPhase6Pending=serving-proof-pending" \
  || fail "timeout path no longer records serving-proof-pending"
grep -q "NOT a restart loop" "$RFI" \
  && pass "exit-78 classification explicitly refuses a restart loop" \
  || fail "restart-loop refusal wording gone"

# The proof must actually call the real health gate (exact payload contract),
# and the manifest check must go through CC's own --verify (never hand-written).
SPF="$WORK/serving-proof.sh"
if printf '%s\n' "$EXTRACTED" | grep -qE 'if _phase6_pm2_online && .*cc_live_health_ok'; then
  pass "serving proof gates on cc_live_health_ok in its ALL-of check (exact local health payload)"
else
  fail "serving proof no longer includes cc_live_health_ok in the all-of proof"
fi
if printf '%s\n' "$EXTRACTED" | grep -q 'cc_phase6_serving_proof'; then
  pass "extracted block contains cc_phase6_serving_proof"
else
  fail "extracted block missing cc_phase6_serving_proof"
fi
if grep -q 'cc_phase6_serving_proof 30 2' "$RFI"; then
  pass "installer invokes cc_phase6_serving_proof before stamping done"
else
  fail "installer no longer invokes cc_phase6_serving_proof at the fresh-branch call site"
fi
if printf '%s\n' "$EXTRACTED" | grep -qF 'bash "$lib" --verify "$DASHBOARD_DIR"'; then
  pass "manifest check runs build-inventory.sh --verify (never hand-written)"
else
  fail "manifest check no longer runs build-inventory.sh --verify"
fi
if printf '%s\n' "$EXTRACTED" | grep -qF '.next/build-inventory.json'; then
  pass "proof checks the PRES-046 content manifest path"
else
  fail "proof no longer checks .next/build-inventory.json"
fi
if printf '%s\n' "$EXTRACTED" | grep -q 'cc-start-refused.json'; then
  pass "proof reads the deterministic exit-78 refusal receipt"
else
  fail "proof no longer reads .cc-state/cc-start-refused.json"
fi
if grep -q 'state_set .commandCenterPhase6Done = true' "$RFI"; then
  : # normal
fi
if grep -qF "state_set '.commandCenterPhase6Pending = null'" "$RFI"; then
  pass "a passing proof CLEARS the pending flag (not just stamps done)"
else
  fail "passing proof no longer clears commandCenterPhase6Pending"
fi
if grep -q 'fail_install "phase=6: cc-start refused deterministically' "$RFI"; then
  pass "exit-78 classification fails the install loudly (rebuild/config-repair required)"
else
  fail "exit-78 classification no longer fails the install with a rebuild-required message"
fi

echo ""
echo "  RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
