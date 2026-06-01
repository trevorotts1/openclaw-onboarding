#!/usr/bin/env bash
# test-department-floor.sh — smoke test for the HARD department floor enforcer.
#
# Proves the four guarantees the floor fix must deliver (all against REAL folders
# on disk, NOT a build-state JSON):
#
#   T1. 16-DEPT FLOOR ENFORCED: a workspace with all 16 mandatory dept folders
#       (no industry signal) PASSES (rc=0).
#   T2. SEEDED 3-DEPT STATE FAILS: a 3-dept-on-disk workspace — even with a
#       hand-seeded build-state claiming closeoutStatus=done/buildCompletedAt —
#       FAILS the floor (rc=3). This is the Cassandra-seeded-fiction bypass.
#   T3. EXPLICIT DECLINE HONORED: a 15-dept workspace where the 16th mandatory is
#       recorded as an explicit decline PASSES (rc=0).
#   T4. VERTICAL PACKS ADD INDUSTRY DEPTS: with a real-estate industry signal, the
#       expected floor GROWS beyond 16 to include the real-estate pack depts, and a
#       16-mandatory-only disk (missing the pack depts) FAILS (rc=3); adding the
#       pack depts then PASSES (rc=0).
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FLOOR="$SCRIPT_DIR/department-floor.py"
NAMING_MAP="$SKILL_DIR/department-naming-map.json"

PASS=0; FAIL=0
ok()   { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Mandatory ids from the naming map (source of truth).
MANDATORY=$(python3 -c "import json;print(' '.join(json.load(open('$NAMING_MAP')).get('mandatory',{}).keys()))")
RE_PACK_DEPTS=$(python3 -c "
import json
d=json.load(open('$NAMING_MAP'))
pk=d.get('vertical_packs',{}).get('real-estate',{})
print(' '.join(x['id'] for x in pk.get('auto_add_departments',[])))
")

mk_workspace() { # <name> <space-separated dept slugs>
  local name="$1"; shift
  local dd="$TMP/zero-human-company/$name/departments"
  rm -rf "$TMP/zero-human-company/$name"
  mkdir -p "$dd"
  for d in "$@"; do
    mkdir -p "$dd/$d/some-role"
  done
  echo "$dd"
}

# Run department-floor.py against an explicit --departments-dir, with an optional
# build-state and core-answers injected by writing a tiny driver that calls
# evaluate_floor() directly (so the test does not depend on detect_platform).
eval_floor() { # <departments_dir> <build_state_json_or_empty> <core_answers_json_or_empty> ; echo rc
  local dd="$1" bs="$2" ca="$3"
  python3 - "$FLOOR" "$dd" "$bs" "$ca" <<'PYEOF'
import json, sys, importlib.util
floor_path, dd, bs_raw, ca_raw = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
spec = importlib.util.spec_from_file_location("department_floor", floor_path)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
from pathlib import Path
bs = json.loads(bs_raw) if bs_raw else {}
ca = json.loads(ca_raw) if ca_raw else {}
v = m.evaluate_floor(departments_dir=Path(dd), build_state=bs, core_answers=ca)
sys.stderr.write(json.dumps({k: v[k] for k in ("rc","expected_floor_count","on_disk_count","missing_mandatory","missing_vertical","declined")}) + "\n")
sys.exit(v["rc"])
PYEOF
}

echo "=== T1: 16-dept floor enforced (all mandatory present, no industry) ==="
DD=$(mk_workspace t1 $MANDATORY)
if eval_floor "$DD" "" '{"industry":"general business"}'; then ok "16 mandatory on disk -> rc=0 (floor met)"; else bad "16 mandatory should PASS but rc!=0"; fi

echo "=== T2: seeded 3-dept state FAILS (Cassandra bypass) ==="
DD=$(mk_workspace t2 marketing sales research)
SEED='{"status":"done","buildCompletedAt":"2026-01-01T00:00:00Z","closeoutStatus":"done","departments":[{"slug":"marketing"},{"slug":"sales"},{"slug":"research"},{"slug":"crm"},{"slug":"legal"},{"slug":"video"},{"slug":"audio"},{"slug":"graphics"},{"slug":"communications"},{"slug":"customer-support"},{"slug":"billing-finance"},{"slug":"web-development"},{"slug":"app-development"},{"slug":"openclaw-maintenance"},{"slug":"social-media"},{"slug":"paid-advertisement"}]}'
if eval_floor "$DD" "$SEED" '{"industry":"coaching"}'; then bad "3-dept disk + seeded done-state should FAIL but rc=0 (BYPASS NOT CLOSED)"; else ok "3 depts on disk -> rc=3 even with seeded done-state + 16 fake dept entries in JSON"; fi

echo "=== T3: explicit decline honored (15 + 1 declined) ==="
# Drop one mandatory ('audio') from disk and record it as an explicit decline.
KEEP=$(for d in $MANDATORY; do [ "$d" != "audio" ] && printf '%s ' "$d"; done)
DD=$(mk_workspace t3 $KEEP)
DECLINE='{"declinedDepartments":["audio"]}'
if eval_floor "$DD" "$DECLINE" '{"industry":"general business"}'; then ok "15 mandatory + explicit decline of 'audio' -> rc=0 (decline honored)"; else bad "explicit decline should PASS but rc!=0"; fi
# And prove the SAME 15-dept disk WITHOUT a decline FAILS.
if eval_floor "$DD" "" '{"industry":"general business"}'; then bad "15 mandatory + NO decline should FAIL but rc=0"; else ok "15 mandatory + NO decline -> rc=3 (missing 'audio', no decline)"; fi

echo "=== T4: vertical packs add industry depts (real-estate) ==="
RE_SIGNAL='{"industry":"real estate brokerage","company_description":"residential real estate agent MLS listings and showings"}'
# 16-mandatory-only disk, but real-estate signal -> floor grows -> pack depts missing -> FAIL.
DD=$(mk_workspace t4a $MANDATORY)
if eval_floor "$DD" "" "$RE_SIGNAL"; then bad "real-estate signal but only 16 mandatory on disk should FAIL (pack depts missing) but rc=0"; else ok "real-estate signal grows floor beyond 16; 16-only disk -> rc=3 (vertical pack depts missing)"; fi
# Now add the real-estate pack depts -> PASS.
DD=$(mk_workspace t4b $MANDATORY $RE_PACK_DEPTS)
if eval_floor "$DD" "" "$RE_SIGNAL"; then ok "16 mandatory + real-estate pack depts on disk -> rc=0 (floor met incl verticals)"; else bad "16 + real-estate pack depts should PASS but rc!=0"; fi

echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL DEPARTMENT-FLOOR SMOKE TESTS PASSED"; exit 0; } || { echo "SMOKE TEST FAILURES"; exit 1; }
