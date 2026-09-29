#!/usr/bin/env bash
# test-pack-keyword-variants.sh -- a vertical-pack keyword matches its listed
# inflected forms in all three keyword matchers (build-workforce's
# _detect_vertical_packs, department-floor's matched_vertical_pack_departments,
# vertical-derivation-guard's declared_packs_from_core_answers), and nothing else.
# A coaching business described as "financial coaching and consulting" matched
# none of "coach" / "consultant" (whole-word only), so its personal-pro-dev
# departments later failed the phase 3b guard as undeclared.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
python3 - "$SCRIPT_DIR" "$SKILL_DIR/department-naming-map.json" <<'PY'
import importlib.util, json, sys
from pathlib import Path
scripts, nm_path = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(scripts))
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, str(scripts / file))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
guard, floor, bw = load("vdg", "vertical-derivation-guard.py"), load("dfl", "department-floor.py"), load("bw", "build-workforce.py")
nm = json.load(open(nm_path))
packs = nm["vertical_packs"]
ppd_extras = {d["id"] for d in packs["personal-pro-dev"]["auto_add_departments"] if not d.get("universal_primary")}

def verdicts(desc, industry=""):
    ca = {"industry": industry, "company_description": desc, "biggest_challenge": "", "tools": ""}
    g = "personal-pro-dev" in guard.declared_packs_from_core_answers(ca, nm)
    f = ppd_extras <= set(floor.matched_vertical_pack_departments(nm, ca))
    b = "personal-pro-dev" in dict(bw._detect_vertical_packs(ca, packs))
    return g, f, b

fail = 0
def expect(desc, want, industry=""):
    global fail
    got = verdicts(desc, industry)
    ok = got == (want, want, want)
    fail |= not ok
    print(f"  {'PASS' if ok else 'FAIL'}: personal-pro-dev {'declared' if want else 'undeclared'} "
          f"(guard, floor, build) = {got} for {desc!r}")

expect("We provide financial coaching and consulting, bookkeeping and tax filing; "
       "members join our Wealth Circle membership.", True, "financial services and tax preparation")
for d in ("career coaches for new managers", "we consult for founders", "a consultants collective",
          "an executive coach"):
    expect(d, True)
# Negative controls: a stem inside another word, and a plain tax business.
for d in ("stagecoach tours and charter buses", "coachella travel packages",
          "tax preparation and bookkeeping for small businesses", "consultative selling software"):
    expect(d, False)
print("RESULT:", "PASS" if not fail else "FAIL")
sys.exit(fail)
PY
