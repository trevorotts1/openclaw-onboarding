#!/usr/bin/env bash
# test-vertical-derivation-guard.sh — U107 (E5-2, closes G2a) acceptance tests
# for vertical-derivation-guard.py: a vertical is NEVER force-added to a
# client who is not that vertical.
#
# Covers the unit's BINARY acceptance criteria verbatim:
#   (a) a fixture interview declaring NO real-estate signal provisions ZERO
#       real-estate department, receipt shows provisioned (subset) declared for
#       every vertical-specific department — PASS/FAIL.
#   (b) a fixture interview that DOES declare real estate provisions the
#       real-estate set (positive case, no false-negative) — PASS/FAIL.
#   (c) a seeded attempt to force-add a non-declared vertical is refused with
#       a named error + receipt, not silently added — PASS/FAIL.
# Plus:
#   (d) fail-closed: no build-state record and no core_answers -> a
#       provisioned vertical-specific dept with unexplained provenance FAILs.
#   (e) universal-primary departments are never gated (present with zero
#       declared verticals still PASSes).
#   (f) LOCKSTEP: declared_packs_from_core_answers() agrees with
#       department-floor.py's matched_vertical_pack_departments() (both derive
#       the same pack-level signal from the same interview haystack) so the
#       two independent keyword-match copies cannot silently drift.
#   (g) --check-add CLI: allowed vs refused (named VERTICAL_NOT_DECLARED
#       error), and universal-primary / non-pack department ids always allowed.
#
# Hermetic: every check drives the module's importable functions directly
# against a tmp departments dir — never touches a real ~/.openclaw, never
# reads/writes outside $TMP. Exit 0 = all pass; non-zero = a check failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD="$SCRIPT_DIR/vertical-derivation-guard.py"
FLOOR="$SCRIPT_DIR/department-floor.py"
NAMING_MAP="$SKILL_DIR/department-naming-map.json"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
case "$TMP" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($TMP)"; exit 2 ;;
esac

# The 6 real-estate department ids (department-naming-map.json v2.6.1: none
# flagged universal_primary, so all 6 are vertical-specific / declaration-gated).
RE_DEPTS=(listings lead-generation showings open-house closing-coordinator local-market-intelligence)

mk_departments_dir() { # <name> <space-separated dept slugs>
  local name="$1"; shift
  local dd="$TMP/departments-$name"
  rm -rf "$dd"
  mkdir -p "$dd"
  for d in "$@"; do
    mkdir -p "$dd/$d/some-role"
  done
  echo "$dd"
}

# Drive evaluate_vertical_derivation() directly (no --out writes during the
# assertion itself; each test that needs the receipt writes it into $TMP
# explicitly and inspects the file).
run_eval() { # <departments_dir> <build_state_json_or_empty> <core_answers_json_or_empty>
  local dd="$1" bs="$2" ca="$3"
  python3 - "$GUARD" "$dd" "$bs" "$ca" <<'PYEOF'
import json, sys, importlib.util
guard_path, dd, bs_raw, ca_raw = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
spec = importlib.util.spec_from_file_location("vertical_derivation_guard", guard_path)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
bs = json.loads(bs_raw) if bs_raw else {}
ca = json.loads(ca_raw) if ca_raw else None
v = m.evaluate_vertical_derivation(departments_dir=dd, build_state=bs, core_answers=ca)
sys.stderr.write(json.dumps(v) + "\n")
sys.exit(v["rc"])
PYEOF
}

echo "=== (a): NO real-estate signal -> zero real-estate depts provisioned, PASS ==="
DD=$(mk_departments_dir a marketing sales research)
BS_NONE='{"verticalPacks":{"detectedPacks":[]}}'
if run_eval "$DD" "$BS_NONE" ""; then
  ok "(a) empty departments-dir (no RE depts) + empty declared set -> rc=0 (PASS, provisioned subset declared)"
else
  bad "(a) should PASS (nothing provisioned, nothing to violate) but rc!=0"
fi
# Same, but core_answers-derived path (no build-state record at all): a
# non-real-estate industry signal must NOT provision real estate.
CA_SAAS='{"industry":"software as a service","company_description":"we build a SaaS analytics dashboard"}'
if run_eval "$DD" "" "$CA_SAAS"; then
  ok "(a) saas core_answers, no RE depts on disk -> rc=0 (PASS)"
else
  bad "(a) saas signal with zero RE depts on disk should PASS but rc!=0"
fi

echo ""
echo "=== (b): interview DOES declare real estate -> full RE set provisions, PASS (no false-negative) ==="
DD=$(mk_departments_dir b "${RE_DEPTS[@]}")
BS_RE='{"verticalPacks":{"detectedPacks":[{"pack":"real-estate","matchedKeywords":["realtor","mls"]}]}}'
if run_eval "$DD" "$BS_RE" ""; then
  ok "(b) all 6 RE depts on disk + real-estate declared (build-state record) -> rc=0 (PASS, positive case honored)"
else
  bad "(b) declared real-estate + fully-provisioned RE set should PASS but rc!=0 (FALSE NEGATIVE)"
fi
CA_RE='{"industry":"real estate brokerage","company_description":"residential realtor, MLS listings and showings"}'
if run_eval "$DD" "" "$CA_RE"; then
  ok "(b) all 6 RE depts on disk + real-estate signal via core_answers (no build-state record) -> rc=0 (PASS)"
else
  bad "(b) core_answers-derived real-estate declaration should PASS the fully-provisioned RE set but rc!=0"
fi

echo ""
echo "=== (c): seeded force-add of a NON-declared vertical is refused, not silently added ==="
# The departments dir HAS a real-estate dept, but the declared set (build-state
# record) is EMPTY (e.g. a coaching client) — this is the "force-add" fixture:
# something put 'listings' on disk without the interview ever declaring it.
DD=$(mk_departments_dir c marketing sales listings)
BS_EMPTY='{"verticalPacks":{"detectedPacks":[]}}'
if run_eval "$DD" "$BS_EMPTY" ""; then
  bad "(c) 'listings' on disk with EMPTY declared set should FAIL but rc=0 (force-add NOT caught)"
else
  ok "(c) 'listings' on disk with EMPTY declared set -> rc=3 (FAIL, force-add refused)"
fi
# Confirm the violation is a NAMED error, not a silent FAIL.
VIOL_JSON=$(run_eval "$DD" "$BS_EMPTY" "" 2>&1 1>/dev/null | tail -1)
if echo "$VIOL_JSON" | python3 -c "import json,sys; v=json.load(sys.stdin); assert v['violations'] and 'VERTICAL_NOT_DECLARED' in v['violations'][0]['reason'] and v['violations'][0]['id']=='listings' and v['violations'][0]['pack']=='real-estate'" 2>/dev/null; then
  ok "(c) violation carries a NAMED error (VERTICAL_NOT_DECLARED) naming dept='listings' pack='real-estate'"
else
  bad "(c) violation JSON missing the expected named-error / id / pack fields"
fi
# The receipt file itself must be written and must show the FAIL verdict + violation.
# (the guard reads build-state from the real default path when --build-state
# is omitted, so pin an explicit empty-declared build-state FILE here — never
# rely on the CLI's default resolution — to keep this assertion hermetic and
# independent of the runner's real HOME/.openclaw.)
RECEIPT_OUT="$TMP/receipt-c.json"
BS_FILE="$TMP/bs-empty.json"
printf '%s' "$BS_EMPTY" > "$BS_FILE"
python3 "$GUARD" --departments-dir "$DD" --build-state "$BS_FILE" --naming-map "$NAMING_MAP" --out "$RECEIPT_OUT" --json >/dev/null 2>"$TMP/receipt-c.stderr"
if [ -f "$RECEIPT_OUT" ] && python3 -c "
import json
r = json.load(open('$RECEIPT_OUT'))
assert r['verdict'] == 'FAIL', r['verdict']
assert r['rc'] == 3, r['rc']
assert any(v['id'] == 'listings' for v in r['violations']), r['violations']
assert r['schemaVersion'] and r['generatedAt'] and r['source']
"; then
  ok "(c) receipt written to disk with verdict=FAIL, rc=3, violation naming 'listings', schema/timestamp/source stamped"
else
  bad "(c) receipt file missing or malformed after a refused force-add audit"
fi

echo ""
echo "=== (d): fail-closed — no build-state record + no core_answers -> unexplained dept FAILs ==="
DD=$(mk_departments_dir d marketing listings)
if run_eval "$DD" "" ""; then
  bad "(d) 'listings' on disk with NO declared-source at all should FAIL (fail-closed) but rc=0"
else
  ok "(d) 'listings' on disk with NO build-state record and NO core_answers -> rc=3 (fail-closed, absence != permission)"
fi

echo ""
echo "=== (e): universal-primary vertical depts are never declaration-gated ==="
# 'engineering' (saas pack) is flagged universal_primary=true in the naming map
# — it should be excluded from the vertical-specific check entirely, i.e.
# present with a completely empty declared set still PASSes.
DD=$(mk_departments_dir e marketing engineering)
if run_eval "$DD" "$BS_EMPTY" ""; then
  ok "(e) universal-primary 'engineering' present + empty declared set -> rc=0 (PASS, universal-primary excluded from the gate)"
else
  bad "(e) universal-primary department should never be declaration-gated but rc!=0"
fi

echo ""
echo "=== (f): LOCKSTEP — guard's keyword match agrees with department-floor.py's ==="
python3 - "$GUARD" "$FLOOR" "$NAMING_MAP" <<'PYEOF'
import json, sys, importlib.util

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

guard = load("vertical_derivation_guard", sys.argv[1])
floor = load("department_floor", sys.argv[2])
nm = json.load(open(sys.argv[3]))

fixtures = [
    {"industry": "software as a service", "company_description": "SaaS analytics"},
    {"industry": "real estate brokerage", "company_description": "residential realtor, MLS listings"},
    {"industry": "general coaching", "company_description": "leadership coaching for executives"},
    {"industry": "", "company_description": "we run a boutique agency for paid ads"},
]

failures = []
for ca in fixtures:
    guard_packs = set(guard.declared_packs_from_core_answers(ca, nm).keys())
    floor_dept_ids = set(floor.matched_vertical_pack_departments(nm, ca))
    # Map floor's matched DEPARTMENT ids back to their pack via the guard's own
    # dept index (single source of dept->pack truth) and drop universal
    # primaries (floor's function includes those; the guard's declared-packs
    # signal is about which packs are KEYWORD-declared, so compare on the
    # keyword-matched (non-universal-primary) subset only).
    idx = guard.dept_pack_index(nm)
    floor_packs_nonuniversal = {idx[d]["pack"] for d in floor_dept_ids if d in idx and not idx[d]["universal_primary"]}
    if guard_packs != floor_packs_nonuniversal:
        failures.append((ca, sorted(guard_packs), sorted(floor_packs_nonuniversal)))

if failures:
    for ca, gp, fp in failures:
        print(f"DRIFT: {ca} -> guard={gp} floor={fp}", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PYEOF
if [ $? -eq 0 ]; then
  ok "(f) guard's declared_packs_from_core_answers() agrees with department-floor.matched_vertical_pack_departments() on 4 fixtures (no drift)"
else
  bad "(f) LOCKSTEP DRIFT between vertical-derivation-guard.py and department-floor.py's keyword-match logic"
fi

echo ""
echo "=== (g): --check-add CLI — allowed vs refused, named error ==="
if python3 "$GUARD" --check-add listings --declared "sales-ops" --naming-map "$NAMING_MAP" >/dev/null 2>"$TMP/g1.err"; then
  bad "(g1) --check-add listings with declared={sales-ops} (real-estate NOT declared) should exit 1 (refused) but exited 0"
else
  ok "(g1) --check-add listings with real-estate undeclared -> exit 1 (refused)"
fi
grep -q "VERTICAL_NOT_DECLARED" "$TMP/g1.err" && ok "(g1) refusal message carries the named error VERTICAL_NOT_DECLARED" || bad "(g1) refusal message missing named error"

if python3 "$GUARD" --check-add listings --declared "real-estate" --naming-map "$NAMING_MAP" >/dev/null 2>"$TMP/g2.err"; then
  ok "(g2) --check-add listings with declared={real-estate} -> exit 0 (allowed)"
else
  bad "(g2) --check-add listings with real-estate declared should be allowed but exited non-zero"
fi

if python3 "$GUARD" --check-add marketing --declared "" --naming-map "$NAMING_MAP" >/dev/null 2>"$TMP/g3.err"; then
  ok "(g3) --check-add marketing (not a vertical-pack dept at all) with nothing declared -> exit 0 (always allowed)"
else
  bad "(g3) a non-vertical-pack department id should never be gated by this guard"
fi

if python3 "$GUARD" --check-add engineering --declared "" --naming-map "$NAMING_MAP" >/dev/null 2>"$TMP/g4.err"; then
  ok "(g4) --check-add engineering (universal-primary saas dept) with nothing declared -> exit 0 (always allowed)"
else
  bad "(g4) a universal-primary vertical department should never be gated by this guard"
fi

echo ""
echo "=== (h): MULTI-PACK departments — attribution must not depend on naming-map order ==="
# department-naming-map.json declares 'community-management' under BOTH
# personal-pro-dev AND content-creator (and 'podcast' under both too). The
# index must therefore not keep only the LAST declaring pack: a personal-pro-dev
# client that legitimately provisioned community-management as a Phase-2 extra
# from personal-pro-dev must NOT be reported as a content-creator violation.
# This is an install-blocking false-FAIL (run-full-install.sh phase=3b treats
# rc=3 as fail_install), so it is asserted in both directions.
if python3 - "$GUARD" "$NAMING_MAP" <<'PYEOF'
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("vdg", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
nm = json.load(open(sys.argv[2]))
idx = m.dept_pack_index(nm)
cm = idx.get("community-management")
assert cm is not None, "community-management missing from the dept index"
assert set(cm["packs"]) >= {"personal-pro-dev", "content-creator"}, cm
pod = idx.get("podcast")
assert pod is not None and set(pod["packs"]) >= {"personal-pro-dev", "content-creator"}, pod
# podcast is universal_primary=true under content-creator -> ANY flag wins.
assert pod["universal_primary"] is True, pod
assert cm["universal_primary"] is False, cm
PYEOF
then
  ok "(h0) dept index records EVERY declaring pack for multi-pack depts; universal_primary is OR-ed across packs"
else
  bad "(h0) dept index collapsed a multi-pack department to a single pack (naming-map-order dependent)"
fi

DD=$(mk_departments_dir h marketing community-management)
BS_PPD='{"verticalPacks":{"detectedPacks":[{"pack":"personal-pro-dev","matchedKeywords":["coach"]}]}}'
if run_eval "$DD" "$BS_PPD" ""; then
  ok "(h1) 'community-management' + declared={personal-pro-dev} -> rc=0 (PASS; declared via one of its owning packs)"
else
  bad "(h1) FALSE FAIL: community-management is declared by personal-pro-dev but the guard rejected it"
fi

# Gate must still hold: no owning pack declared -> still a violation.
if run_eval "$DD" "$BS_EMPTY" ""; then
  bad "(h2) 'community-management' with an EMPTY declared set should still FAIL but rc=0 (GATE WEAKENED)"
else
  ok "(h2) 'community-management' with EMPTY declared set -> rc=3 (FAIL; gate intact for multi-pack depts)"
fi

# And a pack that owns the dept but was NOT declared must not launder it in.
BS_SAAS='{"verticalPacks":{"detectedPacks":[{"pack":"saas","matchedKeywords":["saas"]}]}}'
if run_eval "$DD" "$BS_SAAS" ""; then
  bad "(h3) 'community-management' with declared={saas} (not an owning pack) should FAIL but rc=0 (GATE WEAKENED)"
else
  ok "(h3) 'community-management' with declared={saas} -> rc=3 (FAIL; only OWNING packs can explain it)"
fi

if python3 "$GUARD" --check-add community-management --declared "personal-pro-dev" --naming-map "$NAMING_MAP" >/dev/null 2>"$TMP/h4.err"; then
  ok "(h4) --check-add community-management with declared={personal-pro-dev} -> exit 0 (allowed)"
else
  bad "(h4) FALSE REFUSAL: --check-add community-management should be allowed when personal-pro-dev is declared"
fi

if python3 "$GUARD" --check-add community-management --declared "saas" --naming-map "$NAMING_MAP" >/dev/null 2>"$TMP/h5.err"; then
  bad "(h5) --check-add community-management with declared={saas} should be refused but exited 0 (GATE WEAKENED)"
else
  ok "(h5) --check-add community-management with declared={saas} -> exit 1 (refused)"
fi
grep -q "VERTICAL_NOT_DECLARED" "$TMP/h5.err" && ok "(h5) multi-pack refusal still carries the named error VERTICAL_NOT_DECLARED" || bad "(h5) multi-pack refusal missing named error"

echo ""
echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL VERTICAL-DERIVATION GUARD TESTS PASSED"; exit 0; } || { echo "VERTICAL-DERIVATION GUARD TEST FAILURES"; exit 1; }
