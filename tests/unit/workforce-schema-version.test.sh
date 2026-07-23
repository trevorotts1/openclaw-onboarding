#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

TMPD=$(mktemp -d)
trap "rm -rf $TMPD" EXIT

# Source the library
source "$REPO_ROOT/lib-onboarding-state.sh"

# ---- T1: v1 fixture (no schemaVersion) -> oc_wf_state_migrate stamps v2 ----
WF="$TMPD/.workforce-build-state.json"
cat > "$WF" << 'EOF'
{"interviewComplete":"true","buildCompletedAt":"2024-01-01T00:00:00Z"}
EOF
out=$(oc_wf_state_migrate "$WF" 2>&1) && rc=$? || rc=$?
echo "T1 migrate output: $out"
grep -q '"schemaVersion": 2' "$WF" 2>/dev/null && pass "T1 v1->v2 migration stamp" || fail "T1 v1->v2 migration stamp missing"

# ---- T2: v1 fixture -> oc_wf_state_read says "migrate via" on stderr, returns 0 ----
cat > "$WF" << 'EOF'
{"interviewComplete":"true","buildCompletedAt":"2024-01-01T00:00:00Z"}
EOF
out=$(oc_wf_state_read "$WF" 2>&1) && rc=$? || rc=$?
echo "T2 read output: $out"
# oc_wf_state_read should print the path on success
echo "$out" | grep -q ".workforce-build-state.json" 2>/dev/null && pass "T2 v1 read succeeds" || fail "T2 v1 read failed, rc=$rc got='$out'"

# ---- T3: schemaVersion:999 -> oc_wf_state_read rejects (non-zero) ----
cat > "$WF" << 'EOF'
{"schemaVersion":999,"interviewComplete":true}
EOF
out=$(oc_wf_state_read "$WF" 2>&1) && rc=$? || rc=$?
echo "T3 rc=$rc out=$out"
[ $rc -ne 0 ] && pass "T3 v999 refused (rc=$rc)" || fail "T3 v999 should refuse, got rc=$rc"

# ---- T4: schemaVersion:999 -> oc_wf_state_migrate also rejects ----
cat > "$WF" << 'EOF'
{"schemaVersion":999,"interviewComplete":true}
EOF
out=$(oc_wf_state_migrate "$WF" 2>&1) && rc=$? || rc=$?
echo "T4 rc=$rc out=$out"
[ $rc -ne 0 ] && pass "T4 migrate v999 refused (rc=$rc)" || fail "T4 migrate v999 should refuse, got rc=$rc"

# ---- T5: corrupted JSON -> oc_wf_state_read quarantines and exits non-zero ----
echo "{broken" > "$WF"
out=$(oc_wf_state_read "$WF" 2>&1) && rc=$? || rc=$?
echo "T5 rc=$rc out=$out"
[ $rc -ne 0 ] && pass "T5 corrupt detected (rc=$rc)" || fail "T5 corrupt should fail, got rc=$rc"
# Check quarantine file
ls "$WF.corrupt-"* 2>/dev/null && pass "T5b quarantine file" || fail "T5b no quarantine file"

# ---- T6: valid v2 file -> oc_wf_state_read succeeds ----
cat > "$WF" << 'EOF'
{"schemaVersion":2,"interviewComplete":true,"ownerName":"Test"}
EOF
out=$(oc_wf_state_read "$WF" 2>&1) && rc=$? || rc=$?
echo "T6 rc=$rc out=$out"
[ $rc -eq 0 ] && pass "T6 valid v2 read" || fail "T6 valid v2 read failed, rc=$rc"

# ---- T7: empty file -> oc_wf_state_read returns 0 (normal) ----
touch "$WF"
out=$(oc_wf_state_read "$WF" 2>&1) && rc=$? || rc=$?
echo "T7 rc=$rc out=$out"
[ $rc -eq 0 ] && pass "T7 empty file read" || fail "T7 empty file should succeed, rc=$rc"

# ---- T8: string interviewComplete -> migrate normalizes to boolean ----
cat > "$WF" << 'EOF'
{"interviewComplete":"yes","buildCompletedAt":"2024-01-01T00:00:00Z"}
EOF
out=$(oc_wf_state_migrate "$WF" 2>&1) && rc=$? || rc=$?
echo "T8 migrate output: $out"
ic=$(python3 -c "import json; print(json.load(open('$WF'))['interviewComplete'])")
[ "$ic" = "True" ] && pass "T8 string->bool normalized (yes)" || fail "T8 string->bool failed, got $ic"

# ---- T9: "false" string -> bool false ----
cat > "$WF" << 'EOF'
{"interviewComplete":"false","buildCompletedAt":"2024-01-01T00:00:00Z"}
EOF
out=$(oc_wf_state_migrate "$WF" 2>&1) && rc=$? || rc=$?
ic=$(python3 -c "import json; print(json.load(open('$WF'))['interviewComplete'])")
[ "$ic" = "False" ] && pass "T9 string->bool normalized (false)" || fail "T9 string->bool failed, got $ic"

# ---- T10: migrate adds default keys (ownerName etc.) ----
cat > "$WF" << 'EOF'
{"interviewComplete":true}
EOF
out=$(oc_wf_state_migrate "$WF" 2>&1) && rc=$? || rc=$?
keys=$(python3 -c "import json; print(sorted(json.load(open('$WF')).keys()))")
echo "T10 keys: $keys"
echo "$keys" | grep -q "ownerName" && pass "T10 defaults added (ownerName)" || fail "T10 defaults missing ownerName"
echo "$keys" | grep -q "closeoutStatus" && pass "T10b defaults added (closeoutStatus)" || fail "T10b defaults missing closeoutStatus"

# ---- T11: already v2 file -> oc_wf_state_migrate no-ops (exit 0) ----
cat > "$WF" << 'EOF'
{"schemaVersion":2,"interviewComplete":true,"ownerName":"Already"}
EOF
out=$(oc_wf_state_migrate "$WF" 2>&1) && rc=$? || rc=$?
echo "T11 rc=$rc out=$out"
[ $rc -eq 0 ] && pass "T11 already v2 no-op" || fail "T11 already v2 failed, rc=$rc"

# ---- T12: non-object JSON top level -> oc_wf_state_read quarantines ----
echo '["array","not","object"]' > "$WF"
out=$(oc_wf_state_read "$WF" 2>&1) && rc=$? || rc=$?
echo "T12 rc=$rc out=$out"
[ $rc -ne 0 ] && pass "T12 non-object quarantined (rc=$rc)" || fail "T12 non-object should fail, rc=$rc"
ls "$WF.corrupt-"* 2>/dev/null && pass "T12b quarantine file" || true

# ---- T13: string schemaVersion -> rejected ----
cat > "$WF" << 'EOF'
{"schemaVersion":"two","interviewComplete":true}
EOF
out=$(oc_wf_state_read "$WF" 2>&1) && rc=$? || rc=$?
echo "T13 rc=$rc out=$out"
[ $rc -ne 0 ] && pass "T13 string schemaVersion rejected (rc=$rc)" || fail "T13 should reject string version, rc=$rc"

# ---- T14: oc_wf_state_stamp_version on v1 file stamps v2 ----
cat > "$WF" << 'EOF'
{"interviewComplete":true}
EOF
out=$(oc_wf_state_stamp_version "$WF" 2>&1) && rc=$? || rc=$?
echo "T14 rc=$rc out=$out"
grep -q '"schemaVersion": 2' "$WF" 2>/dev/null && pass "T14 stamp_version stamps v2" || fail "T14 stamp_version failed"

# ---- T15: schemaVersion:0 -> migrate from v0 (nonexistent lower version) to v2 ----
cat > "$WF" << 'EOF'
{"schemaVersion":0,"interviewComplete":"true"}
EOF
out=$(oc_wf_state_migrate "$WF" 2>&1) && rc=$? || rc=$?
echo "T15 rc=$rc out=$out"
grep -q '"schemaVersion": 2' "$WF" 2>/dev/null && pass "T15 migrate v0->v2" || fail "T15 v0->v2 failed"

echo "=== $PASS passed, $FAIL failed ==="
exit $((FAIL > 0 ? 1 : 0))
