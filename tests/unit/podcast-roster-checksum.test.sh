#!/usr/bin/env bash
set -euo pipefail
S="$(cd "$(dirname "$0")"&&pwd)"
R="$(cd "$S/../.."&&pwd)"
P="$R/58-podcast-production-engine/scripts/podbean_publish.sh"
eval "$(sed -n '/^verify_ledger_checksum()/,/^}/p' "$P")"
T="$(mktemp -d "${TMPDIR:-/tmp}/u035-test.XXXXXX")"
trap 'rm -rf "$T"' EXIT;F=0
mr(){ python3 -c "
import json,hashlib
r=dict(state='$2',job_id='u035',updated_at='t',sqlite_job_id='u035')
r['_checksum']=hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
json.dump(r,open('$1','w'),indent=2)
";}
cf(){ python3 -c "import json;d=json.load(open('$1'));d['$2']='$3';json.dump(d,open('$1','w'),indent=2)";}
echo "--- A: corrupt ---";r="$T/a.json";mr "$r" x;cf "$r" state tampered
verify_ledger_checksum "$r"&&{ echo "FAIL A";F=$((F+1));}||echo "PASS A"
echo "--- B: valid ---";r="$T/b.json";mr "$r" pub
verify_ledger_checksum "$r"&&echo "PASS B"||{ echo "FAIL B";F=$((F+1));}
echo "--- C: no checksum ---";r="$T/c.json"
python3 -c "import json;json.dump(dict(state='x',job_id='x',updated_at='t',sqlite_job_id='x'),open('$r','w'),indent=2)"
verify_ledger_checksum "$r"&&echo "PASS C"||{ echo "FAIL C";F=$((F+1));}
echo "--- D: missing ---"
verify_ledger_checksum "$T/nope.json"&&echo "PASS D"||{ echo "FAIL D";F=$((F+1));}
echo "--- E: bad JSON ---";echo bad>"$T/e.json"
verify_ledger_checksum "$T/e.json"&&{ echo "FAIL E";F=$((F+1));}||echo "PASS E"
echo "--- F: truncated ---";r="$T/f.json";mr "$r" done
python3 -c "p=open('$r').read();open('$r','w').write(p[:-20])"
verify_ledger_checksum "$r"&&{ echo "FAIL F";F=$((F+1));}||echo "PASS F"
echo;if [ $F -eq 0 ];then echo "=== ALL PASSED ===";exit 0;else echo "=== $F FAILED ===";exit 1;fi
