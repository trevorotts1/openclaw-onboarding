#!/usr/bin/env bash
# tests/unit/memory-guard.test.sh
#
# Acceptance tests for the nightly memory guard (scripts/memory-guard.py + .sh):
# key check with the backup chain (original provider, OpenRouter nemotron,
# Gemini), idle workers, and the cron that runs it.
#
# 1. The python self-test (fake `openclaw`, no network, no real ~/.openclaw):
#    every decision the chain makes (primary dead -> nemotron, primary + nemotron
#    dead -> gemini, all dead -> off + one client message, primary recovers ->
#    moved back up, transient never switches) plus the idle rules. A floor on the
#    PASS count stops a self-test that quietly stopped running its cases.
# 2. Wiring: ensure-pipeline-crons.sh registers `memory-guard` at 02:15
#    America/New_York as a silent COMMAND cron, once (idempotent), repairs an
#    existing loud copy, and skips cleanly when the script is absent;
#    install.sh copies both files.
# 3. The wrapper: exits 0 on every non-crash path, non-zero only when the python
#    crashed, refuses root, and moves an unwritable TMPDIR under the OpenClaw root.
#
# Hermetic: private $HOME and sandbox, fake `openclaw`, never the real one.
# Exit 0 = all pass. Exit 1 = a failure.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD_PY="$REPO_ROOT/scripts/memory-guard.py"
GUARD_SH="$REPO_ROOT/scripts/memory-guard.sh"
ENSURE="$REPO_ROOT/scripts/ensure-pipeline-crons.sh"
INSTALL="$REPO_ROOT/install.sh"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
MIN_SELFTEST_PASSES=60

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

echo "=== memory-guard.test.sh ==="

echo "--- 1: python self-test (chain, idle, classifier) ---"
python3 -I "$GUARD_PY" --self-test > "$SANDBOX/self.log" 2>&1
RC=$?
PASSES="$(grep -c '^PASS ' "$SANDBOX/self.log")"
FAILS="$(grep -c '^FAIL ' "$SANDBOX/self.log")"
if [ "$RC" -eq 0 ] && [ "$FAILS" -eq 0 ]; then pass "1a: self-test exits 0, no FAIL line"; else fail "1a: self-test rc=$RC, $FAILS FAIL line(s)"; grep '^FAIL ' "$SANDBOX/self.log" | head -10; fi
if [ "$PASSES" -ge "$MIN_SELFTEST_PASSES" ]; then pass "1b: self-test ran $PASSES cases (floor $MIN_SELFTEST_PASSES)"; else fail "1b: self-test ran only $PASSES cases (floor $MIN_SELFTEST_PASSES)"; fi
for want in "original dead -> nemotron chosen" "original + nemotron dead -> gemini chosen" \
            "all three dead -> memory search off, one client message" "original recovers -> moved back up, one patch" \
            "original transient (a lower option works): nothing changes"; do
  if grep -qF "PASS $want" "$SANDBOX/self.log"; then pass "1c: case ran: $want"; else fail "1c: case missing or failing: $want"; fi
done

echo "--- 2: wiring ---"
python3 - "$ENSURE" "$INSTALL" <<'PY' && pass "2a: registered, managed, audited and installed in lockstep" || fail "2a: wiring is not in lockstep (see above)"
import re, sys
ens, ins = (open(p).read() for p in sys.argv[1:3])
bad = []
if not re.search(r'_ensure_health_cron "memory-guard"\s+"15 2 \* \* \*"\s+"memory-guard\.sh"\s+"America/New_York"', ens):
    bad.append("no _ensure_health_cron memory-guard at 15 2 * * * America/New_York")
m = re.search(r'MANAGED_RECONCILE_CRONS=\(\n(.*?)\n\)', ens, re.S)
if not m or "memory-guard" not in re.findall(r'^\s*"([^"]+)"', m.group(1), re.M):
    bad.append("memory-guard missing from MANAGED_RECONCILE_CRONS")
a = re.search(r'for _n in ((?:"[^"]+"\s*\\?\s*)+); do', ens)
if not a or "memory-guard" not in re.findall(r'"([^"]+)"', a.group(1)):
    bad.append("memory-guard missing from the main() audit list")
loop = re.search(r'EMBEDDING-PREVENTION BUNDLE \(items 4-7\).*?for SCRIPT in ([^;]*); do', ins, re.S)
for f in ("memory-guard.sh", "memory-guard.py"):
    if not loop or f not in loop.group(1).split():
        bad.append(f + " missing from the install.sh copy loop")
if bad:
    print("\n".join("    " + b for b in bad))
sys.exit(1 if bad else 0)
PY

mk_box() { # <tag> <with-script 0|1> -> sets H B J C
  local tag="$1" with="$2" s
  H="$SANDBOX/home-$tag"; B="$SANDBOX/bin-$tag"; J="$SANDBOX/jobs-$tag.json"; C="$SANDBOX/calls-$tag.log"
  mkdir -p "$H/.openclaw/scripts" "$H/clawd" "$B"
  for s in index-model-drift-check.sh orphan-temp-sweep.sh disk-usage-alert.sh pre-july14-embedding-migration-check.sh \
           toolsearch-drift-guard.sh agent-browser-reaper.sh bootstrap-validate-daily.sh bootstrap-compact-weekly.sh; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$H/.openclaw/scripts/$s"
  done
  [ "$with" = "1" ] && printf '#!/usr/bin/env bash\nexit 0\n' > "$H/.openclaw/scripts/memory-guard.sh"
  chmod +x "$H/.openclaw/scripts/"*.sh
  printf '%s' '{}' > "$H/.openclaw/openclaw.json"
  printf '#!/usr/bin/env bash\nexec python3 "%s" "$@"\n' "$FIXTURE" > "$B/openclaw"; chmod +x "$B/openclaw"
  printf '[]' > "$J"; : > "$C"
}
run_ensure() { HOME="$H" PATH="$B:$PATH" FAKE_OC_JOBS_FILE="$J" FAKE_OC_CALLS_FILE="$C" bash "$ENSURE" > "$SANDBOX/ensure.log" 2>&1; }
job_field() { # <name> <count|mode|any job field>
  python3 - "$J" "$1" "$2" <<'PY'
import json, sys
path, name, what = sys.argv[1:4]
rows = [j for j in json.load(open(path)) if j.get("name") == name]
if what == "count":
    print(len(rows))
elif not rows:
    print("ABSENT")
elif what == "mode":
    print((rows[0].get("delivery") or {}).get("mode"))
else:
    print(rows[0].get(what))
PY
}

mk_box reg 1; run_ensure
[ "$(job_field memory-guard count)" = "1" ] && pass "2b: memory-guard registered once" || fail "2b: memory-guard count is $(job_field memory-guard count), want 1"
[ "$(job_field memory-guard cron)" = "15 2 * * *" ] && pass "2c: schedule 15 2 * * *" || fail "2c: schedule is $(job_field memory-guard cron)"
[ "$(job_field memory-guard kind)" = "command" ] && pass "2d: COMMAND kind (no model turn)" || fail "2d: kind is $(job_field memory-guard kind)"
[ "$(job_field memory-guard mode)" = "none" ] && pass "2e: born silent (delivery mode none)" || fail "2e: delivery mode is $(job_field memory-guard mode)"
grep -q -- "cron add --name memory-guard .*--tz America/New_York" "$C" && pass "2f: registered in America/New_York (ahead of the 03:00 New York dreaming)" || fail "2f: no --tz America/New_York on the memory-guard registration"
job_field memory-guard command | grep -q "memory-guard.sh$" && pass "2g: runs memory-guard.sh" || fail "2g: command is $(job_field memory-guard command)"
run_ensure
[ "$(job_field memory-guard count)" = "1" ] && pass "2h: a second run adds no second copy (idempotent)" || fail "2h: second run left $(job_field memory-guard count) copies"

mk_box old 1
python3 - "$J" "$H" <<'PY'
import json, sys
json.dump([{"name": "memory-guard", "cron": "15 2 * * *", "agent": "", "message": "", "kind": "command",
            "command": "bash %s/.openclaw/scripts/memory-guard.sh" % sys.argv[2], "id": "pre-mg",
            "delivery": {"mode": "announce", "channel": "last", "to": None},
            "payload": {"kind": "command"}, "schedule": {"expr": "15 2 * * *"}}], open(sys.argv[1], "w"))
PY
run_ensure
[ "$(job_field memory-guard mode)" = "none" ] && pass "2i: an existing loud copy is silenced by the reconcile pass" || fail "2i: existing copy left at delivery mode $(job_field memory-guard mode)"

mk_box nos 0; run_ensure
[ "$(job_field memory-guard count)" = "0" ] && pass "2j: no script on the box (older bundle): skipped, not registered" || fail "2j: registered without a script"

echo "--- 3: wrapper ---"
mk_wrap() { # <tag> <python body> -> WD (a dir holding the wrapper beside a stub memory-guard.py), WH (home)
  WD="$SANDBOX/wrap-$1"; WH="$SANDBOX/wh-$1"
  mkdir -p "$WD" "$WH/.openclaw"
  cp "$GUARD_SH" "$WD/memory-guard.sh"
  printf '%s\n' "$2" > "$WD/memory-guard.py"
}
run_wrap() { env -u OC_ROOT HOME="$WH" "$@" bash "$WD/memory-guard.sh" > "$SANDBOX/wrap.out" 2>&1; }

mk_wrap ok 'import sys; print("stub ran"); sys.exit(0)'
run_wrap; RC=$?
{ [ "$RC" -eq 0 ] && grep -q "stub ran" "$SANDBOX/wrap.out"; } && pass "3a: python rc 0 -> exit 0, python ran" || fail "3a: rc=$RC"
mk_wrap refused 'import sys; sys.exit(2)'
run_wrap; RC=$?
[ "$RC" -eq 0 ] && pass "3b: python rc 2 (refused/misused) -> exit 0, the scheduler never disables the job" || fail "3b: rc=$RC, want 0"
mk_wrap crash 'raise RuntimeError("boom")'
run_wrap; RC=$?
[ "$RC" -ne 0 ] && pass "3c: python crashed -> wrapper exits non-zero (rc=$RC)" || fail "3c: a crash was swallowed (rc=0)"
mk_wrap tmp 'import os, sys; print("TMPDIR=" + os.environ.get("TMPDIR", "")); sys.exit(0)'
run_wrap TMPDIR=/nonexistent-dir-for-test; RC=$?
{ [ "$RC" -eq 0 ] && grep -q "TMPDIR=$WH/.openclaw/memory-guard/tmp" "$SANDBOX/wrap.out" && [ -d "$WH/.openclaw/memory-guard/tmp" ]; } && pass "3d: unwritable TMPDIR replaced by a private dir under the OpenClaw root" || fail "3d: TMPDIR not moved under the OpenClaw root ($(cat "$SANDBOX/wrap.out"))"
run_wrap TMPDIR="$SANDBOX"; RC=$?
grep -q "TMPDIR=$SANDBOX\$" "$SANDBOX/wrap.out" && pass "3e: a writable TMPDIR is left alone" || fail "3e: writable TMPDIR was changed"
mk_wrap root 'print("stub ran")'
mkdir -p "$SANDBOX/rootbin"; printf '#!/bin/sh\necho 0\n' > "$SANDBOX/rootbin/id"; chmod +x "$SANDBOX/rootbin/id"
run_wrap PATH="$SANDBOX/rootbin:$PATH"; RC=$?
{ [ "$RC" -eq 0 ] && grep -q "REFUSED" "$SANDBOX/wrap.out" && ! grep -q "stub ran" "$SANDBOX/wrap.out"; } && pass "3f: root is refused before anything runs" || fail "3f: root was not refused"
mk_wrap noroot 'print("stub ran")'; rm -rf "$WH/.openclaw"
run_wrap; RC=$?
{ [ "$RC" -eq 0 ] && grep -q "SKIPPED" "$SANDBOX/wrap.out" && ! grep -q "stub ran" "$SANDBOX/wrap.out"; } && pass "3g: no OpenClaw root on the box -> skipped, exit 0" || fail "3g: rc=$RC"
mk_wrap noguard 'print("x")'; rm -f "$WD/memory-guard.py"
run_wrap; RC=$?
{ [ "$RC" -eq 0 ] && grep -q "SKIPPED" "$SANDBOX/wrap.out"; } && pass "3h: script missing (older bundle) -> skipped, exit 0" || fail "3h: rc=$RC"

echo "--- 4: real wrapper end to end (fake openclaw: too-old OpenClaw skipped, 2026.10.5 admitted, nothing written) ---"
WH="$SANDBOX/wh-real"; mkdir -p "$WH/.openclaw" "$SANDBOX/real-bin"
printf '{"memory":{"search":{"provider":"gemini"}},"agents":{"entries":{"main":{}}}}' > "$WH/.openclaw/openclaw.json"
printf '#!/bin/sh\necho "OpenClaw 2026.10.4 (old)"\n' > "$SANDBOX/real-bin/openclaw"; chmod +x "$SANDBOX/real-bin/openclaw"
BEFORE="$(cat "$WH/.openclaw/openclaw.json")"
env -u OC_ROOT HOME="$WH" PATH="$SANDBOX/real-bin:$PATH" bash "$GUARD_SH" > "$SANDBOX/real.out" 2>&1; RC=$?
{ [ "$RC" -eq 0 ] && grep -q "older than 2026.10.5" "$SANDBOX/real.out" && [ "$(cat "$WH/.openclaw/openclaw.json")" = "$BEFORE" ]; } && pass "4a: older OpenClaw: exit 0, SKIPPED, config byte-identical" || fail "4a: rc=$RC: $(tail -3 "$SANDBOX/real.out")"
# 2026.10.5 is a client-box build: it must pass the version gate (fake CLI prints no probe JSON, so
# the key check sees a transient error and changes nothing; the config stays byte-identical).
printf '#!/bin/sh\necho "OpenClaw 2026.10.5 (current)"\n' > "$SANDBOX/real-bin/openclaw"; chmod +x "$SANDBOX/real-bin/openclaw"
env -u OC_ROOT HOME="$WH" PATH="$SANDBOX/real-bin:$PATH" bash "$GUARD_SH" > "$SANDBOX/real2.out" 2>&1; RC=$?
{ [ "$RC" -eq 0 ] && ! grep -q "SKIPPED: OpenClaw" "$SANDBOX/real2.out" && grep -q "key check" "$SANDBOX/real2.out" && [ "$(cat "$WH/.openclaw/openclaw.json")" = "$BEFORE" ]; } && pass "4b: OpenClaw 2026.10.5 is admitted (not skipped), config byte-identical" || fail "4b: rc=$RC: $(tail -3 "$SANDBOX/real2.out")"

echo ""
echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
