#!/bin/bash
# tests/unit/skill77-council-scaffold.test.sh: STRUCTURAL-ONLY regression
# test for Skill 77 (Council of Wise Elders), complete package.
#
# WHAT THIS TESTS: the canonical package exists with its layout, the
# SKILL.md frontmatter name and version agreement, the fixed nine-seat
# roster with exact profile labels in config/advisors.json, the Wave 6
# roster entry appearing exactly once, the skill-department-map entry,
# the README inventory row, the registered SOP, and the update-flow
# safety rule that no state or database files live inside the skill
# folder.
#
# WHAT THIS DOES NOT TEST: deliberation. The runtime and the nine
# advisor packs are built and ship in this package; their behavior is
# covered by the runtime suites and the complete-install fixtures, not
# here. Nothing here simulates a council, and a green run certifies
# package structure only.
#
# Usage: bash tests/unit/skill77-council-scaffold.test.sh
# Exit:  0 = all structural assertions passed, 1 = a failure.

set -u
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL="$ROOT/77-council-of-wise-elders"
FAILS=0

ok()   { echo "  ok   $1"; }
bad()  { echo "  FAIL $1"; FAILS=$((FAILS + 1)); }
check(){ if [ "$1" -eq 0 ]; then ok "$2"; else bad "$2"; fi }

echo "Skill 77 council package: structural assertions"

# --- Package and layout ---
[ -d "$SKILL" ]; check $? "skill folder 77-council-of-wise-elders exists"
for f in SKILL.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md \
         QC.md CHANGELOG.md PREREQS.json version skill-version.txt \
         manifest.json qc-council-of-wise-elders.sh \
         config/defaults.json config/advisors.json \
         schemas/README.md references/protocol.md references/scoring.md \
         references/source-policy.md references/model-routing.md \
         references/report-template.md references/install-matrix.md \
         references/troubleshooting.md runtime/package.json \
         runtime/package-lock.json scripts/doctor.mjs \
         scripts/build-bundles.mjs scripts/verify-bundles.mjs \
         scripts/install-runtime.mjs scripts/export-skill22.mjs \
         scripts/qc-council-of-wise-elders.sh assets/portrait-manifest.json; do
  [ -f "$SKILL/$f" ]; check $? "layout file present: $f"
done

# --- Frontmatter name and version agreement ---
grep -q '^name: council-of-wise-elders$' "$SKILL/SKILL.md"
check $? "SKILL.md frontmatter name is council-of-wise-elders"
FM_V="$(grep -m1 '^version:' "$SKILL/SKILL.md" | awk '{print $2}')"
FILE_V="$(tr -d ' \n' < "$SKILL/version" | sed 's/^v//')"
TXT_V="$(tr -d ' \n' < "$SKILL/skill-version.txt" | sed 's/^v//')"
[ -n "$FM_V" ] && [ "$FM_V" = "$FILE_V" ] && [ "$FILE_V" = "$TXT_V" ]
check $? "versions agree (frontmatter=$FM_V version=$FILE_V skill-version.txt=$TXT_V)"

# --- Roster and exact labels (single source: config/advisors.json) ---
python3 - "$SKILL/config/advisors.json" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
expected_ids = ["simon-sinek", "td-jakes", "oprah-winfrey", "tiffany-aliche",
                "russell-brunson", "michelle-obama", "brene-brown",
                "dennis-kimbro", "les-brown"]
ids = [s["seat_id"] for s in cfg["seats"]]
assert ids == expected_ids, f"roster mismatch: {ids}"
for s in cfg["seats"]:
    want = (f"AI perspective inspired by the published work of {s['name']}. "
            "Not the individual and not an endorsement.")
    assert s["profile_label"] == want, f"label mismatch: {s['seat_id']}"
    assert s["pack_status"] == "built_bibliographic_only", f"pack status drift: {s['seat_id']}"
jakes = cfg["seats"][1]
assert len(jakes["lenses"]) == 3, "td-jakes must carry exactly three lenses in one seat"
print("roster + labels ok")
PYEOF
check $? "nine seats in order, exact labels, Jakes three lenses one seat"

# --- Registration ---
N="$(grep '^OC_WAVE6_SKILLS=' "$ROOT/lib-onboarding-state.sh" | grep -o '77-council-of-wise-elders' | wc -l | tr -d ' ')"
[ "$N" = "1" ]; check $? "wave roster entry appears exactly once in OC_WAVE6_SKILLS (found $N)"
grep -q '"skill": "77"' "$ROOT/23-ai-workforce-blueprint/skill-department-map.json"
check $? "skill-department-map.json carries the skill 77 entry"
grep -q '^| 77-council-of-wise-elders |' "$ROOT/README.md"
check $? "README inventory has the 77 row"
[ -f "$ROOT/universal-sops/SOP-COUNCIL-01-COUNCIL-OF-WISE-ELDERS-DELIBERATION.md" ]
check $? "SOP-COUNCIL-01 registered in universal-sops"

# --- Update-flow safety: no state inside the folder ---
if find "$SKILL" \( -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db' \) | grep -q .; then
  bad "no database or state files inside the skill folder"
else
  ok "no database or state files inside the skill folder"
fi

# --- Doctor (full structural verification incl. manifest hash) ---
if command -v node >/dev/null 2>&1; then
  node "$SKILL/scripts/doctor.mjs" --root "$SKILL" >/dev/null 2>&1
  check $? "doctor.mjs passes on the package"
else
  echo "  skip doctor.mjs (node not available)"
fi

echo ""
if [ "$FAILS" -eq 0 ]; then
  echo "skill77-council-scaffold: ALL PASS (structure only; deliberation behavior is covered by the runtime suites and fixtures)"
else
  echo "skill77-council-scaffold: $FAILS FAILURE(S)"
fi
exit "$([ "$FAILS" -eq 0 ] && echo 0 || echo 1)"
