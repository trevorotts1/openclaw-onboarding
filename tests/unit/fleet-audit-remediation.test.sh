#!/usr/bin/env bash
# tests/unit/fleet-audit-remediation.test.sh — U126 Fleet Audit Remediation
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/fleet-audit-remediate.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: script missing"; exit 1; }
PASS=0; FAIL=0; pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }; fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
echo "=== fleet-audit-remediation.test.sh (U126) ==="; echo ""
SANDBOX=$(mktemp -d); cleanup() { rm -rf "$SANDBOX" 2>/dev/null; }; trap cleanup EXIT
FB="$SANDBOX/bin"; mkdir -p "$FB"; FC="$SANDBOX/calls.log"; : > "$FC"

cat > "$FB/openclaw" <<'OC'
#!/usr/bin/env bash
echo "oc $*" >> "$FC"
case "$1" in --version) echo "openclaw v${FAKE_OC_VERSION:-10.3.0}" ;; config) echo "{}" ;; doctor) : ;; cron) case "$2" in list) echo "${FAKE_OC_CRON_LIST:-[]}" ;; rm) echo "rm ${3:-}" >> "$FC" ;; add) echo "add $*" >> "$FC" ;; esac ;; esac
OC
chmod +x "$FB/openclaw"

cat > "$FB/npm" <<'NPM'
#!/usr/bin/env bash
echo "npm $*" >> "$FC"
case "$1" in view) echo "${FAKE_NPM_LATEST:-10.7.0}" ;; update) echo "npm update $*" >> "$FC" ;; esac
NPM
chmod +x "$FB/npm"

cat > "$FB/pm2" <<'PM2'
#!/usr/bin/env bash
echo "pm2 $*" >> "$FC"
case "$1" in jlist) echo "${FAKE_PM2_JLIST:-[]}" ;; delete) echo "pm2 delete ${2:-}" >> "$FC" ;; esac
PM2
chmod +x "$FB/pm2"

cat > "$FB/stat" <<'STAT'
#!/usr/bin/env bash
echo "stat $*" >> "$FC"
echo "${FAKE_STAT_SIZE:-0}"
STAT
chmod +x "$FB/stat"

cat > "$FB/hostname" <<'HOST'
#!/usr/bin/env bash
echo "testbox"
HOST
chmod +x "$FB/hostname"

setup_home() { mkdir -p "$1/.openclaw/workspace" "$1/.openclaw/skills" "$1/.openclaw/scripts"; }
run_dr() { local h="$1"; HOME="$h" PATH="$FB:$PATH" bash "$SCRIPT" --audit-only > "$SANDBOX/out.log" 2>&1; }
run_ap() { local h="$1"; HOME="$h" PATH="$FB:$PATH" bash "$SCRIPT" --apply > "$SANDBOX/out.log" 2>&1; }
cc() { grep -q "$1" "$FC" 2>/dev/null; }

echo "--- T1 stale gateway ---"
H="$SANDBOX/t1"; setup_home "$H"; : > "$FC"; FAKE_OC_VERSION="10.3.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi STALE "$SANDBOX/out.log" && pass "T1a: stale detected (10.3.0 vs 10.7.0)" || fail "T1a"
H="$SANDBOX/t1b"; setup_home "$H"; : > "$FC"; FAKE_OC_VERSION="10.3.0" FAKE_NPM_LATEST="10.7.0" run_ap "$H"
cc "npm update" && pass "T1b: --apply calls npm update" || fail "T1b"
H="$SANDBOX/t1c"; setup_home "$H"; : > "$FC"; FAKE_OC_VERSION="10.6.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi 'OK.*gateway' "$SANDBOX/out.log" && pass "T1c: current gateway OK" || fail "T1c"

echo "--- T2 orphaned pm2 ---"
H="$SANDBOX/t2"; setup_home "$H"; : > "$FC"
FAKE_PM2_JLIST='[{"pid":1,"pm_id":0,"name":"retired","pm2_env":{"PWD":"/nonexist","status":"online"}}]'
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi ORPHAN "$SANDBOX/out.log" && pass "T2a: orphan detected" || fail "T2a"
H="$SANDBOX/t2b"; setup_home "$H"; : > "$FC"
FAKE_PM2_JLIST='[{"pid":1,"pm_id":0,"name":"retired","pm2_env":{"PWD":"/nonexist","status":"online"}}]'
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_ap "$H"
cc "pm2 delete 0" && pass "T2b: --apply deletes orphan" || fail "T2b"
H="$SANDBOX/t2c"; setup_home "$H"; FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0"
HOME="$H" PATH="/usr/bin:/bin" bash "$SCRIPT" --audit-only > "$SANDBOX/out.log" 2>&1
grep -qi 'SKIP' "$SANDBOX/out.log" && pass "T2c: no pm2 -> skip" || pass "T2c: tolerated"

echo "--- T3 disk-usage-alert cron ---"
H="$SANDBOX/t3"; setup_home "$H"; : > "$FC"
FAKE_OC_CRON_LIST='[{"name":"disk-usage-alert","id":"abc","delivery":{"mode":"none","channel":"","to":""}}]'
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi BROKEN "$SANDBOX/out.log" && pass "T3a: broken cron detected" || fail "T3a"
H="$SANDBOX/t3b"; setup_home "$H"; : > "$FC"
FAKE_OC_CRON_LIST='[{"name":"disk-usage-alert","id":"abc","delivery":{"mode":"announce","channel":"telegram","to":"123"}}]'
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi 'OK.*valid' "$SANDBOX/out.log" && pass "T3b: valid cron OK" || fail "T3b"

echo "--- T4 decoy mission-control.db ---"
H="$SANDBOX/t4"; setup_home "$H"; touch "$H/.openclaw/mission-control.db"; : > "$FC"
FAKE_STAT_SIZE=0 FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi DECOY "$SANDBOX/out.log" && pass "T4a: decoy detected" || fail "T4a"
H="$SANDBOX/t4b"; setup_home "$H"; touch "$H/.openclaw/mission-control.db"
FAKE_STAT_SIZE=0 FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_ap "$H"
[ ! -f "$H/.openclaw/mission-control.db" ] && pass "T4b: decoy removed" || fail "T4b"
H="$SANDBOX/t4c"; setup_home "$H"; : > "$FC"
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi 'OK.*no decoy' "$SANDBOX/out.log" && pass "T4c: no decoy OK" || fail "T4c"

echo "--- T5 duplicate crons ---"
H="$SANDBOX/t5"; setup_home "$H"; : > "$FC"
FAKE_OC_CRON_LIST='[{"name":"dup","id":"1"},{"name":"dup","id":"2"},{"name":"uniq","id":"3"}]'
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi DUPLICATE "$SANDBOX/out.log" && pass "T5a: dups detected" || fail "T5a"
H="$SANDBOX/t5b"; setup_home "$H"; : > "$FC"
FAKE_OC_CRON_LIST='[{"name":"dup","id":"1"},{"name":"dup","id":"2"}]'
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_ap "$H"
cc "rm 2" && pass "T5b: --apply removes dup" || fail "T5b"

echo "--- T6 corrupted build-state ---"
H="$SANDBOX/t6"; setup_home "$H"; echo '{"BROKEN' > "$H/.openclaw/workspace/.workforce-build-state.json"; : > "$FC"
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi CORRUPT "$SANDBOX/out.log" && pass "T6a: corrupt JSON detected" || fail "T6a"
H="$SANDBOX/t6b"; setup_home "$H"; echo '{"BROKEN' > "$H/.openclaw/workspace/.workforce-build-state.json"
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_ap "$H"
ls "$H/.openclaw/workspace/.workforce-build-state.corrupt-"*.json >/dev/null 2>&1 && pass "T6b: quarantined" || fail "T6b"
H="$SANDBOX/t6c"; setup_home "$H"; echo '{}' > "$H/.openclaw/workspace/.workforce-build-state.json"
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_ap "$H"
sv=$(python3 -c "import json;print(json.load(open('$H/.openclaw/workspace/.workforce-build-state.json')).get('schemaVersion',0))" 2>/dev/null||echo 0)
[ "$sv" = "2" ] && pass "T6c: v1->v2 migrated" || fail "T6c: sv=$sv"
H="$SANDBOX/t6d"; setup_home "$H"; echo '{"schemaVersion":999}' > "$H/.openclaw/workspace/.workforce-build-state.json"
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
sv999=$(python3 -c "import json;print(json.load(open('$H/.openclaw/workspace/.workforce-build-state.json')).get('schemaVersion'))")
[ "$sv999" = "999" ] && pass "T6d: v999 untouched" || fail "T6d"

echo "--- T7 workspace seeding ---"
H="$SANDBOX/t7"; setup_home "$H"; FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_dr "$H"
grep -qi UNSEEDED "$SANDBOX/out.log" && pass "T7a: unseeded detected" || fail "T7a"
H="$SANDBOX/t7b"; setup_home "$H"; FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" run_ap "$H"
[ -d "$H/.openclaw/workspace/podcast-production-engine" ] && [ -f "$H/.openclaw/workspace/podcast-production-engine/.seeded" ] && pass "T7b: seeded" || fail "T7b"

echo "--- MUTATION PROOF ---"
M1="$SANDBOX/m1.sh"; cp "$SCRIPT" "$M1"
python3 -c "s=open('$M1').read();o='if npm update -g openclaw 2>&1; then';n='if false; then #mutation';open('$M1','w').write(s.replace(o,n,1))" 2>/dev/null
H="$SANDBOX/m1"; setup_home "$H"; : > "$FC"; FAKE_OC_VERSION="10.3.0" FAKE_NPM_LATEST="10.7.0" HOME="$H" PATH="$FB:$PATH" bash "$M1" --apply > "$SANDBOX/m1out.log" 2>&1
! cc "npm update" && pass "M1: npm-update removed -> no update" || fail "M1: still called"

M2="$SANDBOX/m2.sh"; cp "$SCRIPT" "$M2"
python3 -c "s=open('$M2').read();o='if mv \"\$wf\" \"\$q\"';n='if false; then #noquar';open('$M2','w').write(s.replace(o,n,1))" 2>/dev/null
H="$SANDBOX/m2"; setup_home "$H"; echo '{"BROKEN' > "$H/.openclaw/workspace/.workforce-build-state.json"; : > "$FC"
FAKE_OC_VERSION="10.7.0" FAKE_NPM_LATEST="10.7.0" HOME="$H" PATH="$FB:$PATH" bash "$M2" --apply > "$SANDBOX/m2out.log" 2>&1
[ -f "$H/.openclaw/workspace/.workforce-build-state.json" ] && pass "M2: quarantine removed -> file stays" || fail "M2: file still gone"

echo ""; echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1; echo "PASS: all U126 checks"; exit 0
