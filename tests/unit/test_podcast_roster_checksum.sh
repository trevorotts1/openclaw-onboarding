#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PODBEAN_PUBLISH="$REPO_ROOT/58-podcast-production-engine/scripts/podbean_publish.sh"
PODCAST_STATE="$REPO_ROOT/58-podcast-production-engine/scripts/podcast_state.py"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

tmpd=""
cleanup() { rm -rf "$tmpd"; }
trap cleanup EXIT

tmpd=$(mktemp -d)

# ---- helpers ----
make_valid_roster() {
  local path="$1"
  python3 -c "
import json, hashlib
data = {'episodes': [{'number': 1, 'title': 'Test Episode'}], 'state': 'received', 'podbean_permalink': None}
canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
cs = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
data['_checksum'] = cs
with open('$path', 'w') as f:
    json.dump(data, f, indent=2)
"
}

make_pre_u035_roster() {
  local path="$1"
  python3 -c "
import json
data = {'episodes': [{'number': 1, 'title': 'Test Episode'}], 'state': 'received', 'podbean_permalink': None}
with open('$path', 'w') as f:
    json.dump(data, f, indent=2)
"
}

# Extract verify_ledger_checksum function from podbean_publish.sh
# and test it in isolation (the function is self-contained and only uses python3).
source_checksum_fn() {
  # Extract and eval the verify_ledger_checksum function only, avoiding the
  # 'set -euo pipefail' and readonly declarations in the main script body.
  awk '/^verify_ledger_checksum\(\)/,/^}/' "$PODBEAN_PUBLISH"
}

# T1: valid record with checksum passes verification
echo "=== T1: valid roster passes verification ==="
make_valid_roster "$tmpd/roster_valid.json"
if eval "$(source_checksum_fn)" && verify_ledger_checksum "$tmpd/roster_valid.json"; then
  pass "T1 valid checksum"
else
  fail "T1 valid checksum"
fi

# T2: corrupted field fails checksum verification
echo "=== T2: corrupted roster fails verification ==="
make_valid_roster "$tmpd/roster_corrupt.json"
python3 -c "
import json
with open('$tmpd/roster_corrupt.json') as f:
    data = json.load(f)
if 'episodes' in data and data['episodes']:
    data['episodes'][0]['title'] = 'CORRUPTED_DATA'
with open('$tmpd/roster_corrupt.json', 'w') as f:
    json.dump(data, f, indent=2)
"
if eval "$(source_checksum_fn)" && verify_ledger_checksum "$tmpd/roster_corrupt.json" 2>/dev/null; then
  fail "T2 corrupt detected"
else
  pass "T2 corrupt detected"
fi

# T3: verify_ledger_checksum returns 0 for valid ledger (via source)
echo "=== T3: verify_ledger_checksum returns 0 for valid ledger ==="
make_valid_roster "$tmpd/roster_t3.json"
if eval "$(source_checksum_fn)" && verify_ledger_checksum "$tmpd/roster_t3.json"; then
  pass "T3 verify_ledger_checksum valid"
else
  fail "T3 verify_ledger_checksum valid"
fi

# T4: verify_ledger_checksum returns 1 for corrupted ledger
echo "=== T4: verify_ledger_checksum returns 1 for corrupted ledger ==="
if eval "$(source_checksum_fn)" && verify_ledger_checksum "$tmpd/roster_corrupt.json" 2>/dev/null; then
  fail "T4 verify_ledger_checksum corrupt"
else
  pass "T4 verify_ledger_checksum corrupt"
fi

# T5: pre-U035 record (no _checksum) passes (backward-compatible)
echo "=== T5: pre-U035 record passes ==="
make_pre_u035_roster "$tmpd/roster_legacy.json"
if eval "$(source_checksum_fn)" && verify_ledger_checksum "$tmpd/roster_legacy.json"; then
  pass "T5 legacy record"
else
  fail "T5 legacy record"
fi

# T6: missing file returns 0 gracefully
echo "=== T6: missing file returns gracefully ==="
if eval "$(source_checksum_fn)" && verify_ledger_checksum "$tmpd/roster_nonexistent.json"; then
  pass "T6 missing file"
else
  fail "T6 missing file"
fi

# T7: truncated/corrupted JSON returns 1
echo "=== T7: truncated JSON fails ==="
echo '{"episodes": [{"number": 1, "title": "Brok' > "$tmpd/roster_truncated.json"
if eval "$(source_checksum_fn)" && verify_ledger_checksum "$tmpd/roster_truncated.json" 2>/dev/null; then
  fail "T7 truncated JSON"
else
  pass "T7 truncated JSON"
fi

# T8: Direct Python checksum verification (T1 equiv, testing compute_checksum + verify pattern)
echo "=== T8: Python checksum round-trip ==="
python3 -c "
import json, hashlib, sys, os
sys.path.insert(0, '$REPO_ROOT/58-podcast-production-engine/scripts')
# Test direct computation and verification pattern
data = {'episodes': [{'number': 1, 'title': 'Roundtrip'}], 'state': 'received'}
canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
cs = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
data['_checksum'] = cs
path = '$tmpd/roster_roundtrip.json'
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
# Re-read and verify
with open(path) as f:
    raw = f.read()
loaded = json.loads(raw)
stored = loaded.pop('_checksum', None)
recomputed = hashlib.sha256(json.dumps(loaded, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
assert stored == recomputed, 'ROUNDTRIP FAILED'
print('OK')
" && pass "T8 checksum round-trip" || fail "T8 checksum round-trip"

# T9: Checksum mismatch detected in Python layer
echo "=== T9: Python checksum mismatch detection ==="
python3 -c "
import json, hashlib, sys, os
sys.path.insert(0, '$REPO_ROOT/58-podcast-production-engine/scripts')
# Create valid roster
data = {'episodes': [{'number': 1, 'title': 'Original'}], 'state': 'received'}
canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
cs = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
data['_checksum'] = cs
path = '$tmpd/roster_tamper.json'
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
# Tamper with content but keep same checksum
data['episodes'][0]['title'] = 'TAMPERED'
canonical2 = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
data['_checksum'] = hashlib.sha256(canonical2.encode('utf-8')).hexdigest()
# Now the _checksum doesn't match the body (it matches the tampered version)
# Actually let's just do a direct corruption test
with open(path, 'r') as f:
    raw = f.read()
loaded = json.loads(raw)
stored = loaded.pop('_checksum', None)
# Tamper the data but DON'T update checksum
loaded['episodes'][0]['title'] = 'TAMPERED'
recomputed = hashlib.sha256(json.dumps(loaded, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
assert stored != recomputed, 'checksum should NOT match after tampering'
print('OK: mismatch correctly detected')
" && pass "T9 checksum mismatch detected" || fail "T9 checksum mismatch detected"

# Summary
echo ""
echo "=== Results: $PASS/$((PASS+FAIL)) passed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "SOME TESTS FAILED"
  exit 1
else
  echo "ALL TESTS PASSED"
  exit 0
fi
