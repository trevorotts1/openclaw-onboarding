#!/usr/bin/env bash
# test-department-floor.sh — smoke test for the HARD department floor enforcer.
#
# Proves the four guarantees the floor fix must deliver (all against REAL folders
# on disk, NOT a build-state JSON):
#
#   T1. FULL FLOOR ENFORCED: a workspace with all mandatory + universal-primary
#       dept folders (no extra industry signal) PASSES (rc=0). A workspace
#       missing even one mandatory dept FAILS (rc=3).
#   T2. SEEDED 3-DEPT STATE FAILS: a 3-dept-on-disk workspace — even with a
#       hand-seeded build-state claiming closeoutStatus=done/buildCompletedAt —
#       FAILS the floor (rc=3). This is the seeded-fiction bypass.
#   T3. PROVENANCED DECLINE HONORED; FABRICATION VECTOR BLOCKED:
#       - ownerDeclineConfirmed + flat list => PASS
#       - bare declinedDepartments[] without ownerDeclineConfirmed => FAIL (gate holds)
#       - object-form provenance in decisions[] => PASS
#       - bare string "no" without ownerDeclineConfirmed => FAIL (gate holds)
#       - bare string "no" WITH ownerDeclineConfirmed => PASS (backward-compat)
#       - no decline record + missing dept => FAIL
#   T4. KEYWORD-MATCHED EXTRAS ARE FLAVOR NOT FLOOR: with a real-estate industry
#       signal, the base floor (28) still passes even if real-estate extras are
#       absent — they are not gating. Missing a universal-primary vertical (which
#       IS gating) causes FAIL (rc=3).
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

# Mandatory ids and universal-primary vertical ids from the naming map (source of truth).
MANDATORY=$(python3 -c "import json;print(' '.join(json.load(open('$NAMING_MAP')).get('mandatory',{}).keys()))")
UNIVERSAL_PRIMARY=$(python3 - "$NAMING_MAP" <<'PYEOF'
import json, sys
nm = json.load(open(sys.argv[1]))
packs = nm.get("vertical_packs") or {}
ids = []
seen = set()
for pack_id, pack in packs.items():
    if not isinstance(pack, dict):
        continue
    depts = pack.get("auto_add_departments", []) or []
    if not depts:
        continue
    # EXPLICIT-opt-in only (mirrors department-floor.universal_primary_vertical_departments
    # v2.6.1): NO depts[0] fallback, so a pack with no flagged dept (e.g. real-estate,
    # whose listings flag was removed) contributes no universal-floor department.
    primary = None
    for dept in depts:
        if isinstance(dept, dict) and dept.get("universal_primary"):
            primary = dept
            break
    if primary:
        did = primary.get("id")
        if did and did not in seen:
            seen.add(did)
            ids.append(did)
print(" ".join(ids))
PYEOF
)
# The full base floor: all mandatory + all universal-primary verticals.
FULL_FLOOR="$MANDATORY $UNIVERSAL_PRIMARY"

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
debug = {k: v[k] for k in ("rc","expected_floor_count","on_disk_count","missing_mandatory","missing_universal_primary","declined")}
sys.stderr.write(json.dumps(debug) + "\n")
sys.exit(v["rc"])
PYEOF
}

echo "=== T1: full floor enforced (all mandatory + universal-primary present) ==="
DD=$(mk_workspace t1 $FULL_FLOOR)
if eval_floor "$DD" "" '{"industry":"general business"}'; then ok "T1a: all 28 depts on disk -> rc=0 (floor met)"; else bad "T1a: full floor on disk should PASS but rc!=0"; fi
# Missing one mandatory (bugs) — no variant conflict with universals — must FAIL.
# 'bugs' has no CANONICAL_VARIANT_SLUGS entry so it cannot be satisfied by another folder.
KEEP_NO_BUGS=$(for d in $FULL_FLOOR; do [ "$d" != "bugs" ] && printf '%s ' "$d"; done)
DD=$(mk_workspace t1b $KEEP_NO_BUGS)
if eval_floor "$DD" "" '{"industry":"general business"}'; then bad "T1b: 27 depts (missing bugs) should FAIL but rc=0 (floor enforcement broken)"; else ok "T1b: missing mandatory 'bugs' -> rc=3 (floor enforced)"; fi
# Missing one universal-primary (presentations) — must FAIL.
KEEP_NO_PRES=$(for d in $FULL_FLOOR; do [ "$d" != "presentations" ] && printf '%s ' "$d"; done)
DD=$(mk_workspace t1c $KEEP_NO_PRES)
if eval_floor "$DD" "" '{"industry":"general business"}'; then bad "T1c: 27 depts (missing presentations) should FAIL but rc=0 (floor enforcement broken)"; else ok "T1c: missing universal-primary 'presentations' -> rc=3 (floor enforced)"; fi

echo "=== T2: seeded 3-dept state FAILS (seeded-fiction bypass) ==="
DD=$(mk_workspace t2 marketing sales research)
SEED='{"status":"done","buildCompletedAt":"2026-01-01T00:00:00Z","closeoutStatus":"done","departments":[{"slug":"marketing"},{"slug":"sales"},{"slug":"research"},{"slug":"crm"},{"slug":"legal"},{"slug":"video"},{"slug":"audio"},{"slug":"graphics"},{"slug":"communications"},{"slug":"customer-support"},{"slug":"billing-finance"},{"slug":"web-development"},{"slug":"app-development"},{"slug":"openclaw-maintenance"},{"slug":"social-media"},{"slug":"paid-advertisement"}]}'
if eval_floor "$DD" "$SEED" '{"industry":"coaching"}'; then bad "T2: 3-dept disk + seeded done-state should FAIL but rc=0 (BYPASS NOT CLOSED)"; else ok "T2: 3 depts on disk -> rc=3 even with seeded done-state + many fake dept entries in JSON"; fi

echo "=== T3: provenanced decline honored; fabrication vector BLOCKED ==="
# Drop 'bugs' from disk (no variant conflict) and test all decline forms.
# Note: do NOT use 'audio' since its variant 'podcast' is a universal primary and
# would satisfy the audio requirement even with the audio folder absent.
KEEP_NO_BUGS_FULL=$(for d in $FULL_FLOOR; do [ "$d" != "bugs" ] && printf '%s ' "$d"; done)
DD=$(mk_workspace t3 $KEEP_NO_BUGS_FULL)

# T3a: ownerDeclineConfirmed=true + flat declinedDepartments[] — must PASS.
DECLINE_CONFIRMED='{"declinedDepartments":["bugs"],"canonicalReconciliation":{"ownerDeclineConfirmed":true}}'
if eval_floor "$DD" "$DECLINE_CONFIRMED" '{"industry":"general business"}'; then ok "T3a: declinedDepartments[] + ownerDeclineConfirmed=true -> rc=0 (provenanced decline honored)"; else bad "T3a: provenanced flat-list decline should PASS but rc!=0"; fi

# T3b: bare declinedDepartments[] WITHOUT ownerDeclineConfirmed — fabrication vector, must FAIL.
DECLINE_BARE='{"declinedDepartments":["bugs"]}'
if eval_floor "$DD" "$DECLINE_BARE" '{"industry":"general business"}'; then bad "T3b: bare declinedDepartments[] without ownerDeclineConfirmed should FAIL (FABRICATION VECTOR OPEN) but rc=0"; else ok "T3b: bare declinedDepartments[] without ownerDeclineConfirmed -> rc=3 (provenance gate holds)"; fi

# T3c: object-form provenance in decisions[] — no ownerDeclineConfirmed needed, must PASS.
DECLINE_OBJ='{"canonicalReconciliation":{"decisions":{"bugs":{"decision":"no","source":"owner-interview","decidedAt":"2026-06-23T00:00:00Z","decidedBy":"owner"}}}}'
if eval_floor "$DD" "$DECLINE_OBJ" '{"industry":"general business"}'; then ok "T3c: object-form provenance decisions[bugs] -> rc=0 (full provenance honored)"; else bad "T3c: object-form provenance decline should PASS but rc!=0"; fi

# T3d: bare string "no" WITHOUT ownerDeclineConfirmed — fabrication vector, must FAIL.
DECLINE_STR='{"canonicalReconciliation":{"decisions":{"bugs":"no"}}}'
if eval_floor "$DD" "$DECLINE_STR" '{"industry":"general business"}'; then bad "T3d: bare string decisions[bugs]='no' without ownerDeclineConfirmed should FAIL (FABRICATION VECTOR OPEN) but rc=0"; else ok "T3d: bare string 'no' without ownerDeclineConfirmed -> rc=3 (provenance gate holds)"; fi

# T3e: bare string "no" WITH ownerDeclineConfirmed — backward-compat, must PASS.
DECLINE_STR_CONFIRMED='{"canonicalReconciliation":{"ownerDeclineConfirmed":true,"decisions":{"bugs":"no"}}}'
if eval_floor "$DD" "$DECLINE_STR_CONFIRMED" '{"industry":"general business"}'; then ok "T3e: bare string 'no' + ownerDeclineConfirmed=true -> rc=0 (backward-compat honored)"; else bad "T3e: bare string 'no' with ownerDeclineConfirmed should PASS but rc!=0"; fi

# T3f: no decline record at all — must FAIL (bugs missing, not declined).
if eval_floor "$DD" "" '{"industry":"general business"}'; then bad "T3f: mandatory-bugs-missing + NO decline should FAIL but rc=0"; else ok "T3f: mandatory-bugs-missing + NO decline -> rc=3 (missing 'bugs', no decline)"; fi

echo "=== T4: keyword-matched extras are flavor not floor; universal-primary IS gating ==="
RE_SIGNAL='{"industry":"real estate brokerage","company_description":"residential real estate agent MLS listings and showings"}'
# Full base floor (28 depts) + real-estate signal -> PASS (keyword extras are flavor, not gating).
DD=$(mk_workspace t4a $FULL_FLOOR)
if eval_floor "$DD" "" "$RE_SIGNAL"; then ok "T4a: 28-dept base floor + real-estate signal -> rc=0 (keyword extras are flavor, not gating)"; else bad "T4a: full base floor with real-estate signal should PASS (extras are not gating) but rc!=0"; fi
# Missing one universal-primary ('presentations') with real-estate signal -> FAIL.
DD=$(mk_workspace t4b $KEEP_NO_PRES)
if eval_floor "$DD" "" "$RE_SIGNAL"; then bad "T4b: missing universal-primary 'presentations' + real-estate should FAIL but rc=0"; else ok "T4b: missing universal-primary 'presentations' -> rc=3 (universal-primary IS gating)"; fi

echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL DEPARTMENT-FLOOR SMOKE TESTS PASSED"; exit 0; } || { echo "SMOKE TEST FAILURES"; exit 1; }
