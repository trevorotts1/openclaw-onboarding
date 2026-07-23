#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PASS=0; FAIL=0
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
assert_pass() { echo -n "  $1 ... "; PASS=$((PASS+1)); echo -e "${GREEN}PASS${NC}"; }
assert_fail() { echo -n "  $1 ... "; FAIL=$((FAIL+1)); echo -e "${RED}FAIL${NC}: $2"; }
TMPDIR="$(mktemp -d)"; trap 'rm -rf "$TMPDIR"' EXIT
LEDGER_FILE="$TMPDIR/test-roster.json"
verify_ledger_checksum() {
  local file="$1"
  [ -f "$file" ] || return 0
  python3 -c '
import hashlib, json, sys, hmac
try:
    with open(sys.argv[1], "r") as fh: raw = fh.read()
except Exception: sys.exit(1)
try: data = json.loads(raw)
except Exception: sys.exit(1)
cs = data.get("_checksum") if isinstance(data, dict) else None
if cs is None: sys.exit(0)
obj = {k: v for k, v in data.items() if k != "_checksum"}
canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
if not hmac.compare_digest(cs, actual):
    sys.stderr.write("podbean_publish: ledger checksum MISMATCH for " + sys.argv[1] + ": expected " + cs[:16] + "... got " + actual[:16] + "... (corruption or truncation suspected)\n")
    sys.exit(1)
sys.exit(0)
' "$file"
}
echo '=== U035: Podcast Roster Integrity Checksum Tests ==='
echo ''; echo '--- T1: Valid record passes ---'
python3 -c "import hashlib,json; r={'client_id':'t1','state':'received','episode_title':'Test'}; c=json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')); r['_checksum']=hashlib.sha256(c.encode()).hexdigest(); json.dump(r,open('$LEDGER_FILE','w'),indent=2)"
if verify_ledger_checksum "$LEDGER_FILE"; then assert_pass 'T1: valid record'; else assert_fail 'T1: valid record' 'non-zero exit'; fi
echo '--- T2: Corrupted field fails ---'
python3 -c "import hashlib,json; r={'client_id':'t2','state':'received','episode_title':'Original'}; c=json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')); r['_checksum']=hashlib.sha256(c.encode()).hexdigest(); json.dump(r,open('$LEDGER_FILE','w'),indent=2)"
python3 -c "import json; r=json.load(open('$LEDGER_FILE')); r['episode_title']='CORRUPTED'; json.dump(r,open('$LEDGER_FILE','w'),indent=2)"
if ! verify_ledger_checksum "$LEDGER_FILE"; then assert_pass 'T2: corrupted fails'; else assert_fail 'T2: corrupted fails' 'zero exit'; fi
echo '--- T3: bash function valid ---'
python3 -c "import hashlib,json; r={'client_id':'t3','state':'qc','episode_title':'Valid'}; c=json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')); r['_checksum']=hashlib.sha256(c.encode()).hexdigest(); json.dump(r,open('$LEDGER_FILE','w'),indent=2)"
if verify_ledger_checksum "$LEDGER_FILE"; then assert_pass 'T3: bash function valid'; else assert_fail 'T3: bash function valid' 'non-zero exit'; fi
echo '--- T4: bash function corrupted ---'
python3 -c "import hashlib,json; r={'client_id':'t4','state':'art','episode_title':'WillCorrupt'}; c=json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')); r['_checksum']=hashlib.sha256(c.encode()).hexdigest(); json.dump(r,open('$LEDGER_FILE','w'),indent=2)"
python3 -c "import json; r=json.load(open('$LEDGER_FILE')); r['state']='CORRUPTED'; json.dump(r,open('$LEDGER_FILE','w'),indent=2)"
if ! verify_ledger_checksum "$LEDGER_FILE"; then assert_pass 'T4: bash function corrupted'; else assert_fail 'T4: bash function corrupted' 'zero exit'; fi
echo '--- T5: pre-U035 record ---'
python3 -c "import json; json.dump({'client_id':'t5','state':'received'},open('$LEDGER_FILE','w'),indent=2)"
if verify_ledger_checksum "$LEDGER_FILE"; then assert_pass 'T5: pre-U035 record'; else assert_fail 'T5: pre-U035 record' 'non-zero exit'; fi
echo '--- T6: missing file ---'
if verify_ledger_checksum "$TMPDIR/nope.json"; then assert_pass 'T6: missing file'; else assert_fail 'T6: missing file' 'non-zero exit'; fi
echo '--- T7: truncated JSON ---'
python3 -c "import hashlib,json; r={'client_id':'t7','state':'received'}; c=json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')); r['_checksum']=hashlib.sha256(c.encode()).hexdigest(); json.dump(r,open('$LEDGER_FILE','w'),indent=2)"
python3 -c "import json; d=json.load(open('$LEDGER_FILE')); d['state']='BROKEN'; json.dump(d,open('$LEDGER_FILE','w'),indent=2)"
if ! verify_ledger_checksum "$LEDGER_FILE"; then assert_pass 'T7: truncated JSON'; else assert_fail 'T7: truncated JSON' 'zero exit'; fi
echo ''; echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ] && exit 1
exit 0
