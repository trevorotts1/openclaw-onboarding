#!/usr/bin/env bash
# test-naming-map-corruption-fail-closed.sh — P2-06 (d)/(e) break-it, made a
# PERMANENT regression: "corrupt a test copy of the naming map and prove the
# build refuses to go short."
#
# P2-06's root cause (OQ-7): when department-naming-map.json was unreadable,
# the build used to SILENTLY drop to 22 departments (losing the 6
# universal-primary). department-floor.py now carries a documented
# "BROKEN-INSTALL SAFETY NET": mandatory_ids() and
# universal_primary_vertical_departments() both fall back to the hardcoded
# HARDCODED_MANDATORY / HARDCODED_UNIVERSAL_PRIMARY lists (22 + 6 = 28) the
# moment the live map yields nothing usable. That fallback logic existed but
# was NEVER independently exercised by a dedicated corruption test anywhere
# in the suite (test-department-floor.sh's T1-T4 all use the REAL, healthy
# department-naming-map.json) — this is exactly the "UNVERIFIED" residue
# P2-06 (b) called out. This suite closes it permanently.
#
# Every test corrupts ONLY a private tmp COPY of the naming map (via
# monkeypatching department_floor.NAMING_MAP after import — module-level
# globals are looked up at call time in Python, so reassigning the symbol
# redirects load_naming_map()'s open() call without ever touching the real
# repo file). Nothing under the repo checkout is ever written to.
#
#   T1. INVALID JSON + FULL 28-dept workspace on disk -> floor_met=True,
#       expected_floor_count==28 (fallback keeps the full floor, no silent
#       drop to 22).
#   T2. INVALID JSON + a workspace with ONLY the 22 mandatory depts on disk
#       (all 6 universal-primary depts absent) -> floor_met=False, rc=3, and
#       missing_universal_primary reports EXACTLY the 6 hardcoded ids. THE
#       ACCEPTANCE CASE: a corrupted map must NOT let a short board pass as
#       floor_met=True — this is "the build refuses to go short."
#   T3. NAMING MAP FILE DOES NOT EXIST AT ALL (unreadable, not just invalid)
#       + FULL 28-dept workspace -> floor_met=True (same fallback fires on
#       OSError, not just JSONDecodeError).
#   T4. VALID JSON BUT SEMANTICALLY EMPTY ({}), i.e. a naming map that parses
#       fine but carries neither a "mandatory" key nor "vertical_packs" +
#       SHORT workspace -> still rc=3, missing lists still populated from the
#       hardcoded fallback (mandatory_ids()'s `m or list(HARDCODED_MANDATORY)`
#       fires even when json.load() itself succeeds).
#
# Exit 0 = all checks pass; non-zero = a test failed (a corrupted/missing map
# would silently shrink the enforced floor — the exact P2-06 defect, now live
# again).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOOR="$SCRIPT_DIR/department-floor.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ── shared driver: monkeypatches department_floor.NAMING_MAP to a private tmp
#    path (or a nonexistent one) BEFORE calling evaluate_floor(), so the real
#    repo department-naming-map.json is never touched or even opened. ─────────
run_case() { # <case-name> <naming_map_path_or_MISSING> <space-separated-depts-on-disk>
  local case_name="$1"; local map_arg="$2"; shift 2
  local dd="$TMP/ws-$case_name/departments"
  rm -rf "$TMP/ws-$case_name"
  mkdir -p "$dd"
  for d in "$@"; do
    mkdir -p "$dd/$d/some-role"
  done
  python3 - "$FLOOR" "$dd" "$map_arg" <<'PYEOF'
import importlib.util, json, sys
from pathlib import Path

floor_path, dd, map_arg = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("department_floor_corrupttest", floor_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Monkeypatch the module-level NAMING_MAP constant AFTER import — load_naming_map()
# resolves it at CALL time (Python globals lookup), so this redirects open(NAMING_MAP)
# without ever touching the real repo file.
if map_arg == "MISSING":
    m.NAMING_MAP = Path("/nonexistent/does-not-exist/department-naming-map.json")
else:
    m.NAMING_MAP = Path(map_arg)

v = m.evaluate_floor(departments_dir=Path(dd), build_state={}, core_answers={})
out = {
    "rc": v["rc"],
    "floor_met": v["floor_met"],
    "expected_floor_count": v["expected_floor_count"],
    "mandatory_count": len(v["mandatory"]),
    "universal_primary_count": len(v["universal_primary_vertical"]),
    "missing_mandatory": v["missing_mandatory"],
    "missing_universal_primary": v["missing_universal_primary"],
}
print(json.dumps(out))
PYEOF
}

MANDATORY_22="marketing sales billing-finance customer-support web-development app-development graphics video audio research communications crm openclaw-maintenance legal social-media paid-advertisement personal-assistant general-task project-architecture-office bugs healer quality-control"
FULL_28="$MANDATORY_22 presentations scheduling-dispatch logistics-fulfillment engineering account-management podcast"

echo "=== T1: INVALID JSON + full 28-dept workspace -> floor_met=True, floor stays 28 ==="
echo '{ this is not valid json ]]]' > "$TMP/invalid.json"
OUT=$(run_case t1 "$TMP/invalid.json" $FULL_28)
echo "  $OUT"
FLOOR_MET=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['floor_met'])")
EXP=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['expected_floor_count'])")
if [ "$FLOOR_MET" = "True" ] && [ "$EXP" = "28" ]; then
  ok "T1: invalid-JSON map + full floor on disk -> floor_met=True, expected_floor_count=28 (no silent shrink)"
else
  bad "T1: expected floor_met=True and expected_floor_count=28, got floor_met=$FLOOR_MET expected_floor_count=$EXP"
fi

echo "=== T2 (ACCEPTANCE CASE): INVALID JSON + only the 22 mandatory on disk -> rc=3, all 6 universal-primary MISSING ==="
OUT=$(run_case t2 "$TMP/invalid.json" $MANDATORY_22)
echo "  $OUT"
RC=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['rc'])")
MISSING_UP_COUNT=$(echo "$OUT" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['missing_universal_primary']))")
if [ "$RC" = "3" ] && [ "$MISSING_UP_COUNT" = "6" ]; then
  ok "T2: corrupted map did NOT let a 22-only board pass -- rc=3, 6 universal-primary depts correctly flagged missing"
else
  bad "T2 (THE ACCEPTANCE CASE): expected rc=3 and 6 missing universal-primary, got rc=$RC missing_universal_primary_count=$MISSING_UP_COUNT -- A CORRUPTED MAP LET THE FLOOR GO SHORT"
fi

echo "=== T3: naming map FILE DOES NOT EXIST (unreadable, OSError not JSONDecodeError) + full 28-dept workspace -> floor_met=True ==="
OUT=$(run_case t3 "MISSING" $FULL_28)
echo "  $OUT"
FLOOR_MET=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['floor_met'])")
EXP=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['expected_floor_count'])")
if [ "$FLOOR_MET" = "True" ] && [ "$EXP" = "28" ]; then
  ok "T3: missing naming-map file + full floor on disk -> floor_met=True, expected_floor_count=28"
else
  bad "T3: expected floor_met=True and expected_floor_count=28, got floor_met=$FLOOR_MET expected_floor_count=$EXP"
fi

echo "=== T4: VALID but semantically-empty JSON ({}) + only 22 mandatory on disk -> rc=3, fallback still fires ==="
echo '{}' > "$TMP/empty.json"
OUT=$(run_case t4 "$TMP/empty.json" $MANDATORY_22)
echo "  $OUT"
RC=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['rc'])")
MAND_COUNT=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['mandatory_count'])")
UP_COUNT=$(echo "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['universal_primary_count'])")
if [ "$RC" = "3" ] && [ "$MAND_COUNT" = "22" ] && [ "$UP_COUNT" = "6" ]; then
  ok "T4: valid-but-empty {} map -> mandatory_ids()/universal_primary_vertical_departments() still fall back to 22+6=28 (not just an exception path)"
else
  bad "T4: expected rc=3, mandatory_count=22, universal_primary_count=6, got rc=$RC mandatory_count=$MAND_COUNT universal_primary_count=$UP_COUNT"
fi

echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL NAMING-MAP-CORRUPTION FAIL-CLOSED TESTS PASSED"; exit 0; } || { echo "NAMING-MAP-CORRUPTION FAIL-CLOSED TESTS FAILED"; exit 1; }
