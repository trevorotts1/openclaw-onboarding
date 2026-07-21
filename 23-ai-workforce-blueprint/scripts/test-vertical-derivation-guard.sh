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
# TIGHTENED (was: only asserted rc!=0). 'listings' is now covered by the dated
# universal_primary_history table, so "still FAILs" is no longer self-evident —
# it FAILs because this fixture offers no evidence of PRE-reclassification
# provisioning. Assert that REASON, not just the exit code: a future change that
# loosened the witness rule would keep rc=3 here by luck, and this assertion is
# what would catch it.
if echo "$VIOL_JSON" | python3 -c "
import json,sys
v=json.load(sys.stdin)
r=v['violations'][0]['reason']
assert 'GRANDFATHER REFUSED' in r, r
assert 'NO_PRE_RECLASSIFICATION_WITNESS' in r, r
assert not v.get('grandfatheredDepartments'), v.get('grandfatheredDepartments')
" 2>/dev/null; then
  ok "(c) force-add of 'listings' with no pre-reclassification evidence is refused a grandfather BY NAME (NO_PRE_RECLASSIFICATION_WITNESS), not merely rc=3"
else
  bad "(c) 'listings' force-add did not carry the explicit grandfather-refusal reason"
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
# TIGHTENED: a missing declaration record must be REPORTED, not silently
# absorbed into the verdict. Assert the named warning exists on this path.
D_JSON=$(run_eval "$DD" "" "" 2>&1 1>/dev/null | tail -1)
if echo "$D_JSON" | python3 -c "
import json,sys
v=json.load(sys.stdin)
assert any('NO_DECLARATION_RECORD' in w for w in v.get('warnings',[])), v.get('warnings')
assert v['residueSummary']['declarationRecordPresent'] is False, v['residueSummary']
" 2>/dev/null; then
  ok "(d) missing verticalPacks record is REPORTED as NO_DECLARATION_RECORD + residueSummary.declarationRecordPresent=false (never silently absorbed)"
else
  bad "(d) missing declaration record was not reported in warnings/residueSummary"
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
echo "=== (i): RETROACTIVE-RECLASSIFICATION GRANDFATHERING (universal_primary_history) ==="
# b3e25876 (v14.28.1, 2026-06-28T15:26:48Z) removed universal_primary=true from
# real-estate/'listings'. Before it, apply_vertical_packs PHASE 1 added EVERY
# pack's primary to EVERY client unconditionally, so pre-2026-06-28 clients hold
# 'listings' as FLOOR, not as a force-added vertical. Judging that provisioning
# by today's classification is a clock error, and it is install-blocking.
# These cases pin BOTH halves: the grandfather fires on evidence, and it stays
# unreachable without it.

# i0 — the demotion table itself must be well-formed and self-consistent with
# the live naming map, or nothing below means anything.
if python3 - "$GUARD" "$NAMING_MAP" <<'PYEOF'
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("vdg", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
nm = json.load(open(sys.argv[2]))
table, warns = m.universal_primary_demotions(nm)
assert not warns, f"live naming map produced demotion-table warnings: {warns}"
assert "listings" in table, f"listings missing from the demotion table: {sorted(table)}"
row = table["listings"]
assert row["pack"] == "real-estate", row
assert row["demoted_by_commit"].startswith("b3e25876"), row
idx = m.dept_pack_index(nm)
# The row's premise: listings must NOT be universal_primary today (else stale).
assert idx["listings"]["universal_primary"] is False, idx["listings"]
# And the 6 that ARE still universal primaries must NOT be in the table.
for did in ("engineering", "podcast", "presentations", "scheduling-dispatch",
            "logistics-fulfillment", "account-management"):
    assert idx[did]["universal_primary"] is True, (did, idx[did])
    assert did not in table, f"{did} is still universal_primary but appears in the demotion table"
PYEOF
then
  ok "(i0) demotion table is well-formed and self-consistent with the live naming map (listings demoted by b3e25876; the 6 surviving primaries are absent from it)"
else
  bad "(i0) demotion table is malformed or contradicts the live naming map"
fi

# i1 — THE UNBLOCK: a pre-reclassification box holding 'listings', with NO
# verticalPacks record at all (the fleet-majority shape), PASSES on evidence.
DD_PRE=$(mk_departments_dir i1 marketing sales listings)
BS_PRE='{"buildCompletedAt":"2026-06-20T05:23:46Z","closeoutCompletedAt":"2026-06-21T00:00:00Z"}'
if run_eval "$DD_PRE" "$BS_PRE" ""; then
  ok "(i1) pre-2026-06-28 box with 'listings' and no declaration record -> rc=0 (grandfathered on a dated witness)"
else
  bad "(i1) pre-reclassification 'listings' still FAILs — the retroactive-rule-change block is not lifted"
fi
I1_JSON=$(run_eval "$DD_PRE" "$BS_PRE" "" 2>&1 1>/dev/null | tail -1)
if echo "$I1_JSON" | python3 -c "
import json,sys
v=json.load(sys.stdin)
g=v['grandfatheredDepartments']
assert len(g)==1 and g[0]['id']=='listings', g
assert g[0]['demotedByCommit'].startswith('b3e25876'), g[0]
assert g[0]['witness']['source'].startswith('build-state.buildCompletedAt'), g[0]['witness']
assert g[0]['witness']['strength']=='build-window', g[0]['witness']
assert 'GRANDFATHERED_PRE_RECLASSIFICATION' in g[0]['reason'], g[0]['reason']
assert not v['violations'], v['violations']
assert any('GRANDFATHERED_RESIDUE' in w for w in v['warnings']), v['warnings']
assert any('NO_DECLARATION_RECORD' in w for w in v['warnings']), v['warnings']
assert v['residueSummary']['grandfatheredIds']==['listings'], v['residueSummary']
assert 'grandfathered' in v['reason'], v['reason']
" 2>/dev/null; then
  ok "(i1) the PASS is LOUD: grandfathered dept named with its demoting commit + witness, residueSummary populated, GRANDFATHERED_RESIDUE + NO_DECLARATION_RECORD warnings, verdict reason says 'grandfathered'"
else
  bad "(i1) grandfathered residue is not fully reported on the PASS path"
fi

# i2 — a box whose ONLY evidence postdates the reclassification gets nothing.
DD_POST=$(mk_departments_dir i2 marketing listings)
BS_POST='{"buildCompletedAt":"2026-07-15T00:00:00Z","closeoutCompletedAt":"2026-07-16T00:00:00Z"}'
if run_eval "$DD_POST" "$BS_POST" ""; then
  bad "(i2) post-reclassification 'listings' from an undeclared pack should stay rc=3 but PASSED (GATE WEAKENED)"
else
  ok "(i2) post-reclassification 'listings' from an undeclared pack -> rc=3 (FATAL; no pre-demotion witness)"
fi

# i3 — the DISQUALIFIER outranks circumstantial pre-dating: the build's own
# record naming 'listings' as added by a POST-demotion run must FAIL even though
# buildCompletedAt predates the demotion. Without this, one stale box-level
# timestamp would launder a genuine post-demotion force-add.
DD_MIX=$(mk_departments_dir i3 marketing listings)
BS_MIX='{"buildCompletedAt":"2026-06-20T05:23:46Z","verticalPacks":{"detectedPacks":[],"addedDepartments":[{"id":"listings","pack":"real-estate"}],"appliedAt":"2026-07-10T12:00:00Z"}}'
if run_eval "$DD_MIX" "$BS_MIX" ""; then
  bad "(i3) 'listings' RECORDED as added 2026-07-10 (post-demotion) should stay rc=3 but PASSED (GATE WEAKENED)"
else
  ok "(i3) build record naming 'listings' as a post-demotion add -> rc=3, even with a pre-demotion buildCompletedAt present"
fi
I3_JSON=$(run_eval "$DD_MIX" "$BS_MIX" "" 2>&1 1>/dev/null | tail -1)
echo "$I3_JSON" | grep -q "POST_DEMOTION_ADD" \
  && ok "(i3) refusal names POST_DEMOTION_ADD (direct record beats circumstantial pre-dating)" \
  || bad "(i3) post-demotion add refusal missing the POST_DEMOTION_ADD named reason"

# i4 — the grandfather CANNOT reach a department that was never a universal
# primary, however old the box is. These are the real-estate/coaching leaks the
# guard exists to catch.
for NEVER in showings closing-coordinator lead-generation client-coaches course-creator; do
  DD_N=$(mk_departments_dir "i4-$NEVER" marketing "$NEVER")
  if run_eval "$DD_N" "$BS_PRE" ""; then
    bad "(i4) '$NEVER' (never a universal primary) on a pre-2026-06-28 box should stay rc=3 but PASSED (GATE WEAKENED)"
  else
    ok "(i4) '$NEVER' (never a universal primary) from an undeclared pack -> rc=3 even with a pre-demotion witness"
  fi
done

# i5 — grandfathering never authorizes a NEW add. check_add() must ignore the
# demotion table entirely; this is the single edit that would turn an
# evidence-based grandfather into a blanket bypass.
if python3 "$GUARD" --check-add listings --declared "sales-ops" --naming-map "$NAMING_MAP" >/dev/null 2>"$TMP/i5.err"; then
  bad "(i5) --check-add listings with real-estate undeclared must STILL be refused (grandfathering must not leak into the add path) but exited 0"
else
  ok "(i5) --check-add listings still refused despite listings being in universal_primary_history (grandfather explains old residue, never permits a new add)"
fi
grep -q "VERTICAL_NOT_DECLARED" "$TMP/i5.err" \
  && ok "(i5) add-path refusal still carries VERTICAL_NOT_DECLARED" \
  || bad "(i5) add-path refusal lost its named error"

# i6 — a MALFORMED / OVERREACHING demotion row must be IGNORED and WARNED, never
# honored. Each of these rows, if honored, would widen the gate.
if python3 - "$GUARD" "$NAMING_MAP" "$TMP" <<'PYEOF'
import json, os, sys, importlib.util
spec = importlib.util.spec_from_file_location("vdg", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
base = json.load(open(sys.argv[2]))
tmp = sys.argv[3]

good = {"department": "listings", "pack": "real-estate",
        "demoted_at": "2026-06-28T15:26:48Z", "demoted_by_commit": "b3e25876"}
bad_rows = {
    "missing demoted_by_commit": {k: v for k, v in good.items() if k != "demoted_by_commit"},
    "missing demoted_at":        {k: v for k, v in good.items() if k != "demoted_at"},
    "wildcard department":       dict(good, department="*"),
    "still universal_primary":   dict(good, department="engineering", pack="saas"),
    "not a pack department":     dict(good, department="marketing", pack="real-estate"),
    "unparseable demoted_at":    dict(good, demoted_at="last tuesday"),
    "not an object":             "listings",
}
for label, row in bad_rows.items():
    nm = json.loads(json.dumps(base))
    nm["universal_primary_history"] = {"demotions": [row]}
    table, warns = m.universal_primary_demotions(nm)
    assert table == {}, f"{label}: honored a bad row -> {table}"
    assert warns, f"{label}: dropped a bad row SILENTLY (no warning)"

# demotions[] itself not a list -> nothing grandfathered, loud warning
nm = json.loads(json.dumps(base))
nm["universal_primary_history"] = {"demotions": "all"}
table, warns = m.universal_primary_demotions(nm)
assert table == {} and any("DEMOTION_TABLE_MALFORMED" in w for w in warns), (table, warns)

# and end-to-end: a bad row cannot rescue a pre-dated 'listings'
nm = json.loads(json.dumps(base))
nm["universal_primary_history"] = {"demotions": [dict(good, department="*")]}
dd = os.path.join(tmp, "i6-departments"); os.makedirs(os.path.join(dd, "listings"), exist_ok=True)
v = m.evaluate_vertical_derivation(departments_dir=dd,
                                   build_state={"buildCompletedAt": "2026-06-20T00:00:00Z"},
                                   naming_map=nm)
assert v["rc"] == 3, v
assert not v["grandfatheredDepartments"], v["grandfatheredDepartments"]
assert any("DEMOTION_ROW_IGNORED" in w for w in v["warnings"]), v["warnings"]
PYEOF
then
  ok "(i6) malformed/overreaching demotion rows (missing commit, missing date, wildcard, still-universal, non-pack dept, unparseable date, non-object, non-list table) are ALL ignored WITH a warning and grandfather nothing"
else
  bad "(i6) a malformed or overreaching demotion row was honored, or dropped silently"
fi

# i7 — a witness must clear the cutoff by more than the timezone safety margin,
# so a naive local timestamp written near the demotion can never be what flips a
# violation into a grandfather.
DD_EDGE=$(mk_departments_dir i7 marketing listings)
BS_EDGE='{"buildCompletedAt":"2026-06-28T14:00:00Z"}'
if run_eval "$DD_EDGE" "$BS_EDGE" ""; then
  bad "(i7) a witness 1h26m before the cutoff is inside the timezone safety margin and must NOT grandfather, but PASSED"
else
  ok "(i7) a witness inside the timezone safety margin does not grandfather -> rc=3 (naive-timestamp ambiguity cannot flip the verdict)"
fi

# i8 — the grandfather must not fire when the department is legitimately
# DECLARED: a real real-estate client passes through the declaration path, with
# an EMPTY residue inventory (nothing to clean up).
DD_RE2=$(mk_departments_dir i8 "${RE_DEPTS[@]}")
if run_eval "$DD_RE2" "$BS_RE" ""; then
  ok "(i8) genuine real-estate client (real-estate declared) -> rc=0, unchanged by this feature"
else
  bad "(i8) REGRESSION: declared real-estate client no longer passes"
fi
I8_JSON=$(run_eval "$DD_RE2" "$BS_RE" "" 2>&1 1>/dev/null | tail -1)
if echo "$I8_JSON" | python3 -c "
import json,sys
v=json.load(sys.stdin)
assert v['grandfatheredDepartments']==[], v['grandfatheredDepartments']
assert v['residueSummary']['grandfatheredCount']==0, v['residueSummary']
assert not any('GRANDFATHERED_RESIDUE' in w for w in v['warnings']), v['warnings']
" 2>/dev/null; then
  ok "(i8) a DECLARED department is never routed through the grandfather (residue inventory empty for the real real-estate client)"
else
  bad "(i8) declared real-estate client was wrongly reported as grandfathered residue"
fi

# i9 — the RECEIPT is the cleanup driver: it must carry the residue inventory,
# and the human stderr must print it even on a PASS.
RECEIPT_I9="$TMP/receipt-i9.json"
BS_I9_FILE="$TMP/bs-i9.json"
printf '%s' "$BS_PRE" > "$BS_I9_FILE"
python3 "$GUARD" --departments-dir "$DD_PRE" --build-state "$BS_I9_FILE" --naming-map "$NAMING_MAP" \
  --out "$RECEIPT_I9" >/dev/null 2>"$TMP/i9.stderr"
I9_RC=$?
if [ "$I9_RC" -eq 0 ] && [ -f "$RECEIPT_I9" ] && python3 -c "
import json
r=json.load(open('$RECEIPT_I9'))
assert r['verdict']=='PASS' and r['rc']==0, (r['verdict'], r['rc'])
g=r['grandfatheredDepartments']
assert len(g)==1 and g[0]['id']=='listings', g
assert g[0]['witness']['value'] and g[0]['demotedAt'], g[0]
assert r['residueSummary']['grandfatheredIds']==['listings'], r['residueSummary']
assert r['residueSummary']['declarationRecordPresent'] is False, r['residueSummary']
assert r['warnings'], r['warnings']
assert r['schemaVersion'] and r['generatedAt'] and r['source']
"; then
  ok "(i9) receipt at --out carries grandfatheredDepartments + witness + residueSummary + warnings on a rc=0 run (cleanup is data-driven, no fresh survey needed)"
else
  bad "(i9) receipt missing the residue inventory on the PASS path"
fi
grep -q "GRANDFATHERED RESIDUE" "$TMP/i9.stderr" \
  && ok "(i9) human output prints GRANDFATHERED RESIDUE on stderr even when rc=0 (a clean exit is never silent)" \
  || bad "(i9) rc=0 run printed nothing about the grandfathered residue"
grep -q "RESIDUE INVENTORY" "$TMP/i9.stderr" \
  && ok "(i9) human output prints the RESIDUE INVENTORY summary line" \
  || bad "(i9) rc=0 run printed no residue inventory summary"

echo ""
echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL VERTICAL-DERIVATION GUARD TESTS PASSED"; exit 0; } || { echo "VERTICAL-DERIVATION GUARD TEST FAILURES"; exit 1; }
