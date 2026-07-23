#!/usr/bin/env bash
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/fleet-audit-remediate.sh"
FB="$REPO_ROOT/tests/unit/fixtures-fleet"
[ -f "$SCRIPT" ] || { echo "FAIL: script missing"; exit 1; }
[ -d "$FB" ] || { echo "FAIL: fixture dir missing"; exit 1; }
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
echo "=== fleet-audit-remediation.test.sh (U126) ==="; echo ""

S=$(mktemp -d); trap 'rm -rf $S' EXIT
setup() { mkdir -p "$1/.openclaw/workspace" "$1/.openclaw/skills" "$1/.openclaw/scripts"; }
# Run script and save output. NOT chained with pipefail.
run() {
  local mode="$1" home="$2" outfile="$3"; shift 3
  local ex=()
  for kv in "$@"; do ex+=("$kv"); done
  env "${ex[@]}" HOME="$home" PATH="$FB:$PATH" bash "$SCRIPT" "--${mode}" > "$outfile" 2>&1 || true
}

echo "--- T1: stale gateway ---"
H="$S/t1"; setup "$H"
run audit-only "$H" "$S/t1a.txt" FAKE_OC_VERSION=10.3.0 FAKE_NPM_LATEST=10.7.0
grep -qi STALE "$S/t1a.txt" && pass "T1a: stale detected" || fail "T1a"
run apply "$H" "$S/t1b.txt" FAKE_OC_VERSION=10.3.0 FAKE_NPM_LATEST=10.7.0
grep -q NPM-UPDATE-CALLED "$S/t1b.txt" && pass "T1b: npm update" || fail "T1b"
H2="$S/t1c"; setup "$H2"
run audit-only "$H2" "$S/t1c.txt" FAKE_OC_VERSION=10.5.0 FAKE_NPM_LATEST=10.7.0
grep -qi 'behind=2' "$S/t1c.txt" && pass "T1c: current OK" || fail "T1c"

echo "--- T2: orphaned pm2 ---"
H="$S/t2"; setup "$H"
run audit-only "$H" "$S/t2a.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0 FAKE_PM2_JLIST='[{"pid":1,"pm_id":0,"name":"old","pm2_env":{"PWD":"/ghost","status":"online"}}]'
grep -qi ORPHAN "$S/t2a.txt" && pass "T2a: orphan detected" || fail "T2a"
run apply "$H" "$S/t2b.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0 FAKE_PM2_JLIST='[{"pid":1,"pm_id":0,"name":"old","pm2_env":{"PWD":"/ghost","status":"online"}}]'
grep -q PM2-DELETE-CALLED "$S/t2b.txt" && pass "T2b: pm2 delete" || fail "T2b"

echo "--- T3: disk-usage-alert ---"
H="$S/t3"; setup "$H"
run audit-only "$H" "$S/t3a.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0 FAKE_OC_CRON_LIST='[{"name":"disk-usage-alert","id":"x","delivery":{"mode":"none","channel":"","to":""}}]'
grep -qi BROKEN "$S/t3a.txt" && pass "T3a: broken" || fail "T3a"
H2="$S/t3b"; setup "$H2"
run audit-only "$H2" "$S/t3b.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0 FAKE_OC_CRON_LIST='[{"name":"disk-usage-alert","id":"x","delivery":{"mode":"announce","channel":"tg","to":"123"}}]'
grep -qi 'valid delivery' "$S/t3b.txt" && pass "T3b: valid" || fail "T3b"

echo "--- T4: decoy ---"
H="$S/t4"; setup "$H"; touch "$H/.openclaw/mission-control.db"
run audit-only "$H" "$S/t4a.txt" FAKE_STAT_SIZE=0 FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0
grep -qi DECOY "$S/t4a.txt" && pass "T4a: decoy detected" || fail "T4a"
H2="$S/t4b"; setup "$H2"; touch "$H2/.openclaw/mission-control.db"
run apply "$H2" "$S/t4b.txt" FAKE_STAT_SIZE=0 FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0
[ ! -f "$H2/.openclaw/mission-control.db" ] && pass "T4b: decoy removed" || fail "T4b"

echo "--- T5: duplicates ---"
H="$S/t5"; setup "$H"
run audit-only "$H" "$S/t5a.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0 FAKE_OC_CRON_LIST='[{"name":"dup","id":"1"},{"name":"dup","id":"2"}]'
grep -qi DUPLICATE "$S/t5a.txt" && pass "T5a: dups detected" || fail "T5a"
run apply "$H" "$S/t5b.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0 FAKE_OC_CRON_LIST='[{"name":"dup","id":"1"},{"name":"dup","id":"2"}]'
grep -q "FIXED: removed" "$S/t5b.txt" && pass "T5b: dup removed" || fail "T5b"

echo "--- T6: build-state ---"
H="$S/t6"; setup "$H"; echo "NOTJSON" > "$H/.openclaw/workspace/.workforce-build-state.json"
run audit-only "$H" "$S/t6a.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0
grep -qi CORRUPT "$S/t6a.txt" && pass "T6a: corrupt detected" || fail "T6a"
H2="$S/t6b"; setup "$H2"; echo "NOTJSON" > "$H2/.openclaw/workspace/.workforce-build-state.json"
run apply "$H2" "$S/t6b.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0
grep -q "FIXED: quarantined" "$S/t6b.txt" && pass "T6b: quarantined" || fail "T6b"
H3="$S/t6c"; setup "$H3"; echo '{}' > "$H3/.openclaw/workspace/.workforce-build-state.json"
run apply "$H3" "$S/t6c.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0
svv=$(python3 -c "import json;print(json.load(open('$H3/.openclaw/workspace/.workforce-build-state.json')).get('schemaVersion',0))" 2>/dev/null||echo 0)
[ "$svv" = "2" ] && pass "T6c: v1->v2 ($svv)" || fail "T6c: sv=$svv"
H4="$S/t6d"; setup "$H4"; echo '{"schemaVersion":999}' > "$H4/.openclaw/workspace/.workforce-build-state.json"
run audit-only "$H4" "$S/t6d.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0
svf=$(python3 -c "import json;print(json.load(open('$H4/.openclaw/workspace/.workforce-build-state.json')).get('schemaVersion'))")
[ "$svf" = "999" ] && pass "T6d: v999 untouched" || fail "T6d: sv=$svf"

echo "--- T7: workspace ---"
H="$S/t7"; setup "$H"
run audit-only "$H" "$S/t7a.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0
grep -qi UNSEEDED "$S/t7a.txt" && pass "T7a: unseeded detected" || fail "T7a"
H2="$S/t7b"; setup "$H2"
run apply "$H2" "$S/t7b.txt" FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0
[ -d "$H2/.openclaw/workspace/podcast-production-engine" ] && pass "T7b: seeded" || fail "T7b"

echo "--- MUTATION PROOF ---"
M1="$S/m1.sh"; cp "$SCRIPT" "$M1"
python3 -c "
s=open('$M1').read();s=s.replace('if npm update -g openclaw 2>&1; then','if false; then #MUT',1);open('$M1','w').write(s.replace('else _finding','#_finding'))
" 2>/dev/null
HM="$S/m1"; setup "$HM"
	env FAKE_OC_VERSION=10.3.0 FAKE_NPM_LATEST=10.7.0 HOME="$HM" PATH="$FB:$PATH" bash "$M1" --apply > "$S/m1.txt" 2>&1 || true
! grep -q NPM-UPDATE-CALLED "$S/m1.txt" && pass "M1: npm removed" || fail "M1: npm still called"

M2="$S/m2.sh"; cp "$SCRIPT" "$M2"
python3 << PYMUT
s=open('$M2').read()
s=s.replace('if mv "\$wf" "\$q"','if false; then #x',1)
open('$M2','w').write(s)
PYMUT
HM2="$S/m2"; setup "$HM2"; echo "NOTJSON" > "$HM2/.openclaw/workspace/.workforce-build-state.json"
env FAKE_OC_VERSION=10.7.0 FAKE_NPM_LATEST=10.7.0 HOME="$HM2" PATH="$FB:$PATH" bash "$M2" --apply > "$S/m2.txt" 2>&1 || true
[ -f "$HM2/.openclaw/workspace/.workforce-build-state.json" ] && pass "M2: no quarantine" || fail "M2: file vanished"

echo ""; echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1; echo "PASS: all U126"; exit 0
