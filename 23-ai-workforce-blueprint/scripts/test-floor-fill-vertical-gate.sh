#!/usr/bin/env bash
# test-floor-fill-vertical-gate.sh — the INDUSTRY GATE on floor-fill-driver.py.
# ─────────────────────────────────────────────────────────────────────────────
# THE DEFECT THIS LOCKS (found live on 2026-07-21, four boxes):
#
#   b3e25876 (v14.28.1, 2026-06-28) demoted real-estate/`listings` out of the
#   universal floor so it would stop landing on generic/coaching/consulting
#   boxes. build-workforce.apply_vertical_packs was fixed and department-floor.py
#   agreed. But the UPDATE path never consulted either of them:
#
#     update-skills.sh
#       -> migrate-existing-workforce.sh --apply  (Step 2b)
#          -> detect-stale-artifacts.py   (verdict derived ONLY from
#             templates/role-library/_index.json — which ships EVERY department,
#             including industry-gated ones, and has no vertical-pack concept)
#          -> make-gap-from-staleness.py  (every MISSING role becomes a gap item)
#          -> floor-fill-driver.py --apply  (mkdir'd the absent department)
#
#   so `listings` was re-created on EVERY box on EVERY update — including boxes
#   running the POST-demotion naming map (v2.6.2), and including a box whose
#   owner had EXPLICITLY declined the vertical set in build-state.
#
#   The repo believed this was impossible: floor-wipe-fix-guard.yml's own header
#   asserted the update-path fill "only ever fills missing ROLES/SOPS inside a
#   department that ALREADY EXISTS on disk — a department that is entirely
#   absent was invisible to it (make-gap-from-staleness.py deliberately drops
#   'dept'-kind items)". Dropping `kind: "dept"` items never mattered: the
#   department is reconstructed implicitly from its `kind: "role"` items.
#
# T1 is the REPRODUCTION and FAILS on the pre-fix tree (the driver creates
# `listings` from a role-only gap on a box with no declaration). Do not weaken
# it. T2-T6 lock the gate's scope so the fix cannot become a floor regression.
#
#   T1  absent industry-gated dept + undeclared box   -> NOT created (gate fires)
#   T2  absent industry-gated dept + DECLARED box     -> created (no regression)
#   T3  mandatory/canonical dept (sales)              -> always created (ungated)
#   T4  universal-primary vertical (podcast)          -> always created (ungated)
#   T5  industry-gated dept ALREADY on disk           -> still filled, never
#                                                        removed, never emptied
#   T6  a gated skip is rc 0 (policy skip), never rc 3, and is REPORTED
#
# Hermetic: mktemp sandbox, no network, no git, python3 only. Never reads or
# writes any real box workspace — every scenario pins --workspace at a sandbox
# tree and drops its own .workforce-build-state.json fixture beside it, which is
# the FIRST candidate the gate's resolver consults (see run_ffd below).
# Exit 0 = all checks pass. Exit 1 = one or more failed.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FFD="$SCRIPT_DIR/floor-fill-driver.py"
GUARD="$SCRIPT_DIR/vertical-derivation-guard.py"
NAMING_MAP="$SKILL_DIR/department-naming-map.json"
IDX="$SKILL_DIR/templates/role-library/_index.json"

# create_role_workspaces resolves OpenClaw's platform paths at call time and
# aborts on a CI runner that has neither /data/.openclaw nor ~/.openclaw.
# OPENCLAW_PLATFORM is the documented override for exactly that; every scenario
# passes an explicit --workspace so this only satisfies the platform probe.
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

PASSED=0
FAILED=0
ok()   { echo "  PASS: $*"; PASSED=$((PASSED+1)); }
bad()  { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
fail() { echo "FAIL: $*" >&2; exit 1; }

[ -f "$FFD" ]        || fail "floor-fill-driver.py not shipped at $FFD"
[ -f "$GUARD" ]      || fail "vertical-derivation-guard.py not shipped at $GUARD"
[ -f "$NAMING_MAP" ] || fail "department-naming-map.json not shipped at $NAMING_MAP"
[ -f "$IDX" ]        || fail "role-library _index.json not shipped at $IDX"
python3 -m py_compile "$FFD" || fail "py_compile floor-fill-driver.py failed"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/floor-fill-vertical-gate.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

# ── PREMISE CHECK — the fixture department must really be industry-gated TODAY.
# If `listings` ever regains universal_primary (or leaves the real-estate pack),
# these scenarios would silently test nothing. Assert the premise from the LIVE
# naming map rather than assuming it.
python3 - "$NAMING_MAP" <<'PY' || fail "premise check failed"
import json, sys
nm = json.load(open(sys.argv[1]))
packs = nm.get("vertical_packs") or {}
re_pack = packs.get("real-estate") or {}
entry = next((d for d in re_pack.get("auto_add_departments", []) or []
              if isinstance(d, dict) and d.get("id") == "listings"), None)
assert entry is not None, "real-estate pack no longer declares 'listings'"
assert not entry.get("universal_primary"), "'listings' is universal_primary again — fixture invalid"
pod = packs.get("content-creator") or {}
p = next((d for d in pod.get("auto_add_departments", []) or []
          if isinstance(d, dict) and d.get("id") == "podcast"), None)
assert p is not None and p.get("universal_primary"), "'podcast' is no longer a universal primary — T4 fixture invalid"
print("premise OK: listings=industry-gated(real-estate), podcast=universal-primary")
PY
ok "premise: 'listings' is industry-gated and 'podcast' is universal-primary in the LIVE naming map"

# Real listings role slugs straight out of the shipped manifest — the fixture is
# canonical, never invented.
LROLE="$(python3 - "$IDX" <<'PY'
import json, sys
rs = [r["slug"] for r in json.load(open(sys.argv[1]))["roles"] if r.get("dept") == "listings"]
print(rs[0] if rs else "")
PY
)"
[ -n "$LROLE" ] || fail "could not read a listings role slug from the shipped manifest"

SROLE="$(python3 - "$IDX" <<'PY'
import json, sys
rs = [r["slug"] for r in json.load(open(sys.argv[1]))["roles"] if r.get("dept") == "sales"]
print(rs[0] if rs else "")
PY
)"
[ -n "$SROLE" ] || fail "could not read a sales role slug from the shipped manifest"

PROLE="$(python3 - "$IDX" <<'PY'
import json, sys
rs = [r["slug"] for r in json.load(open(sys.argv[1]))["roles"] if r.get("dept") == "podcast"]
print(rs[0] if rs else "")
PY
)"
[ -n "$PROLE" ] || fail "could not read a podcast role slug from the shipped manifest"

# Gap-maps: role-only, exactly the shape make-gap-from-staleness.py emits for a
# department that is entirely absent from disk.
printf '{"listings": {"kind": "roster", "missing_roles": ["%s"]}}\n' "$LROLE" > "$TMP/gap-listings.json"
printf '{"sales": {"kind": "roster", "missing_roles": ["%s"]}}\n'    "$SROLE" > "$TMP/gap-sales.json"
printf '{"podcast": {"kind": "roster", "missing_roles": ["%s"]}}\n'  "$PROLE" > "$TMP/gap-podcast.json"

# Build-state fixtures. The UNDECLARED one carries a real, well-formed
# verticalPacks record whose detectedPacks is EMPTY — the honest "the interview
# declared no vertical" state, not a missing file.
cat > "$TMP/bs-undeclared.json" <<'JSON'
{"verticalPacks": {"detectedPacks": [], "addedDepartments": []}}
JSON
cat > "$TMP/bs-realestate.json" <<'JSON'
{"verticalPacks": {"detectedPacks": [{"pack": "real-estate",
  "matchedKeywords": ["real estate", "listings"]}], "addedDepartments": []}}
JSON

# IMPORTANT — the invocation below uses ONLY the three flags the PRE-FIX driver
# already accepted (--gap-file / --workspace / --apply). The build-state fixture
# is placed at <workspace>/../.workforce-build-state.json, exactly where a real
# box carries it and where the gate's resolver looks FIRST. If this helper
# passed a new flag instead, the pre-fix tree would exit 2 on argparse and every
# assertion below would "fail" for the wrong reason — a fail-before that proves
# nothing. Keeping the command line identical across both trees is what makes
# T1's reproduction real. It is also what keeps this suite hermetic: the
# workspace-adjacent fixture always resolves first, so no real box build-state
# is ever consulted.
run_ffd() {  # run_ffd <workspace-departments-dir> <gap> <build-state-fixture>
  local ws="$1" gap="$2" bs="$3"
  cp "$bs" "$(dirname "$ws")/.workforce-build-state.json"
  python3 "$FFD" --gap-file "$gap" --workspace "$ws" --apply \
    > "$TMP/out.json" 2> "$TMP/out.err"
  RC=$?
}

# The driver's stdout is NOT pure JSON: create_role_workspaces.py prints its own
# `[library-fill] ...` progress lines to stdout before the report whenever a role
# is actually built. Extract the report from the first `{` (the same tolerance
# materialize-missing-departments.verify_board_join applies) and NEVER traceback
# — a probe that explodes turns one clear failure into unreadable noise.
# Deliberately a fixed set of NAMED checks (no eval / no expression string): the
# probe must not be able to run arbitrary code from its own arguments.
report_check() {  # report_check gated <dept> | report_check unfilled-zero
  python3 - "$TMP/out.json" "$@" <<'PY'
import json, sys
try:
    raw = open(sys.argv[1], encoding="utf-8").read()
    i = raw.find("{")
    r = json.loads(raw[i:]) if i >= 0 else {}
except Exception:
    r = {}
check = sys.argv[2]
if check == "gated":
    sys.exit(0 if sys.argv[3] in (r.get("depts_vertical_gated") or {}) else 1)
if check == "unfilled-zero":
    sys.exit(0 if r.get("unfilled", 1) == 0 else 1)
sys.exit(1)
PY
}

echo ""
echo "=== T1 (REPRODUCTION) — absent industry-gated dept on an UNDECLARED box is NOT created ==="
WS1="$TMP/t1/departments"; mkdir -p "$WS1"
run_ffd "$WS1" "$TMP/gap-listings.json" "$TMP/bs-undeclared.json"
if [ -d "$WS1/listings" ]; then
  bad "'listings' WAS created on a box that declared no vertical — the gate did not fire (pre-fix behavior)"
else
  ok "'listings' was NOT created on a box that declared no vertical"
fi
if report_check gated listings; then
  ok "the refusal is REPORTED under depts_vertical_gated (not a silent drop)"
else
  bad "the skip is not reported in depts_vertical_gated — a silent skip is as bad as a silent add"
fi
if grep -q "VERTICAL_NOT_DECLARED" "$TMP/out.json" "$TMP/out.err"; then
  ok "the refusal carries the guard's NAMED error (VERTICAL_NOT_DECLARED)"
else
  bad "no VERTICAL_NOT_DECLARED named error in the report/stderr"
fi

echo ""
echo "=== T6 — a gated skip is a POLICY SKIP: rc 0, never rc 3 ==="
if [ "$RC" -eq 0 ]; then
  ok "gated skip exits 0 (an industry policy skip must not fail every fleet update)"
else
  bad "gated skip exited $RC — this would print WORKFORCE-PROVISIONING INCOMPLETE on every box"
fi
if report_check unfilled-zero; then
  ok "a gated dept is not counted as an unfilled gap"
else
  bad "a gated dept was counted as unfilled — that turns the gate into a fleet-wide failure"
fi

echo ""
echo "=== T2 — the SAME dept IS created when the box DECLARED that vertical ==="
WS2="$TMP/t2/departments"; mkdir -p "$WS2"
run_ffd "$WS2" "$TMP/gap-listings.json" "$TMP/bs-realestate.json"
if [ -d "$WS2/listings" ] && [ -n "$(find "$WS2/listings" -maxdepth 1 -type d -name "*${LROLE}")" ]; then
  ok "'listings' IS created for a declared real-estate box (the gate is not a blanket block)"
else
  ok_dir="$(ls -1 "$WS2" 2>/dev/null | tr '\n' ' ')"
  bad "'listings' was NOT created for a DECLARED real-estate box (rc=$RC, dirs='${ok_dir}') — the gate over-blocks"
fi

echo ""
echo "=== T3 — a mandatory canonical department is never gated ==="
WS3="$TMP/t3/departments"; mkdir -p "$WS3"
run_ffd "$WS3" "$TMP/gap-sales.json" "$TMP/bs-undeclared.json"
if [ -d "$WS3/sales" ] && [ -n "$(find "$WS3/sales" -maxdepth 1 -type d -name "*${SROLE}")" ]; then
  ok "canonical 'sales' is still materialized on an undeclared box (floor untouched)"
else
  bad "canonical 'sales' was blocked (rc=$RC) — the gate leaked onto the mandatory floor"
fi

echo ""
echo "=== T4 — a UNIVERSAL-PRIMARY vertical is never gated ==="
WS4="$TMP/t4/departments"; mkdir -p "$WS4"
run_ffd "$WS4" "$TMP/gap-podcast.json" "$TMP/bs-undeclared.json"
if [ -d "$WS4/podcast" ]; then
  ok "universal-primary 'podcast' is still materialized on an undeclared box"
else
  bad "universal-primary 'podcast' was blocked (rc=$RC) — the gate leaked onto the universal floor"
fi

echo ""
echo "=== T5 — an industry-gated dept ALREADY on disk is still filled, never removed ==="
WS5="$TMP/t5/departments"; mkdir -p "$WS5/listings/00-seed"
printf 'seed\n' > "$WS5/listings/00-seed/how-to.md"
BEFORE_SEED="$(shasum "$WS5/listings/00-seed/how-to.md" | awk '{print $1}')"
run_ffd "$WS5" "$TMP/gap-listings.json" "$TMP/bs-undeclared.json"
if [ -d "$WS5/listings" ]; then
  ok "a pre-existing industry-gated department is NOT removed (removal is an owner decision)"
else
  bad "the gate DELETED a pre-existing department — it must only ever refuse to CREATE"
fi
if [ -n "$(find "$WS5/listings" -maxdepth 1 -type d -name "*${LROLE}")" ]; then
  ok "roles are still filled into a pre-existing industry-gated department (no floor regression)"
else
  bad "an existing department stopped being filled (rc=$RC) — the gate must only cover ABSENT depts"
fi
AFTER_SEED="$(shasum "$WS5/listings/00-seed/how-to.md" | awk '{print $1}')"
[ "$BEFORE_SEED" = "$AFTER_SEED" ] \
  && ok "pre-existing content is byte-identical (still no-clobber)" \
  || bad "the run clobbered pre-existing content"

echo ""
echo "=== T7 — the gate reads the naming map, not a private list ==="
if python3 - "$FFD" <<'PY'
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
body = src.split('"""', 2)[2] if src.count('"""') >= 2 else src
# No department id literal may be hard-coded in the CODE (docstring excluded):
# the industry-gated set must come from vertical-derivation-guard/naming map.
bad = [d for d in ("listings", "lead-generation", "showings", "open-house",
                   "closing-coordinator", "local-market-intelligence",
                   "field-operations", "reviews-management", "recurring-service",
                   "merchandising", "devops", "brand-partnerships")
       if re.search(r'["\']' + re.escape(d) + r'["\']', body)]
sys.exit(1 if bad else 0)
PY
then
  ok "floor-fill-driver.py hard-codes NO industry-department list (single source of truth preserved)"
else
  bad "floor-fill-driver.py hard-codes an industry-department literal — that is a fourth copy of the list"
fi

echo ""
echo "──────────────────────────────────────────────"
echo "  floor-fill-vertical-gate: $PASSED passed, $FAILED failed"
echo "──────────────────────────────────────────────"
if [ "$FAILED" -ne 0 ]; then
  echo "FAIL: test-floor-fill-vertical-gate.sh — $FAILED check(s) failed" >&2
  exit 1
fi
echo "PASS: test-floor-fill-vertical-gate.sh — an industry-gated department can no longer be force-created on a box that never declared that vertical"
