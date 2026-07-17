#!/usr/bin/env bash
# test-reconciliation-engine.sh - department-reconciliation engine regression guard.
#
# Proves the reconciliation capabilities (PRD R2.1-R2.6) from a clean checkout
# (no live OpenClaw install required), so a regression is caught on every push.
# These are the engine behaviors built into Skill 23 build-workforce.py +
# department-floor.py:
#
#   R2.1  Floor is 23 mandatory + 6 universal-primary = 29, computed live; no
#         stale 16/19/22/26/28 strings remain in the three scripts.
#   R2.2  Capability 1 MERGE custom+floor still works (custom dept preserved).
#   R2.3  Capability 2 semantic COMBINE/MERGE: a custom dept that semantically
#         overlaps a canonical dept under a NON-slug name (Accounting ->
#         billing-finance) is DETECTED as a proposal; on a recorded "merge"
#         decision it is FOLDED into the canonical dept and the duplicate is
#         DROPPED; on "keep" both stay; with no decision it stays PENDING.
#   R2.4  Capability 3 per-dept CUSTOM ROLES are materialized at build.
#   R2.5  Capability 4 per-dept CUSTOM SOPs are captured at build, respecting the
#         canonical/custom boundary gate (canonical = overlay, custom = source).
#   R2.6  Capability 5 symmetric OPT-OUT: a declined universal-primary vertical is
#         SKIPPED by apply_vertical_packs() exactly as a declined mandatory dept.
#
# It also asserts that NO Ant Farm fold-in capability exists in the engine
# (correction: Ant Farm is Trevor-only, never a shared fleet/repo capability).
#
# Exit 0 on pass, 1 on any failure.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 - "$SKILL_DIR" <<'PY'
import sys, os, json, importlib.util, tempfile, re

SKILL = sys.argv[1]
SCRIPTS = os.path.join(SKILL, "scripts")

spec = importlib.util.spec_from_file_location("bw", os.path.join(SCRIPTS, "build-workforce.py"))
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)

fail = 0
def check(cond, msg):
    global fail
    if cond:
        print(f"  ✓ {msg}")
    else:
        print(f"  ✗ {msg}")
        fail = 1

# Isolate all build-state writes/reads to a temp file.
_tmpdir = tempfile.mkdtemp()
_state = os.path.join(_tmpdir, "state.json")
bw._build_state_path = lambda: _state
def _seed_state(obj):
    with open(_state, "w") as f:
        json.dump(obj, f)
def _read_state():
    try:
        with open(_state) as f:
            return json.load(f)
    except Exception:
        return {}

print("== R2.1 floor is 29 (23 + 6), computed live; no stale strings ==")
import subprocess
out = subprocess.run(["python3", os.path.join(SCRIPTS, "list-canonical-departments.py"), "--json"],
                     capture_output=True, text=True)
d = json.loads(out.stdout)
# v2.6.1: real-estate `listings` lost its universal_primary flag (industry-gated now)
# so universal primaries dropped 7 -> 6 and the live floor dropped 29 -> 28.
# U118: 'funnels' registered as a mandatory department, so mandatory rose 22 -> 23
# and the live floor rose back 28 -> 29.
check(d["floor"] == 29, f"list-canonical floor == 29 (got {d['floor']})")
check(d["mandatory_count"] == 23, f"mandatory == 23 (got {d['mandatory_count']})")
check(d["universal_primary_count"] == 6, f"universal-primary == 6 (got {d['universal_primary_count']})")

# Stale-number scan across the three reconciliation scripts (defended strings only:
# we forbid the specific stale floor phrasings the PRD called out).
stale_pat = re.compile(r"canonical[- ]?16|16 mandatory|16\s*\+\s*7|16\+7|23-dept|below 23|= 23\b|= 26\b|19 mandatory")
for fn in ("build-workforce.py", "department-floor.py", "list-canonical-departments.py"):
    txt = open(os.path.join(SCRIPTS, fn)).read()
    hits = stale_pat.findall(txt)
    check(not hits, f"{fn}: no stale 16/19/23/26 floor strings (found {hits})")

print("== R2.2 Capability 1: custom dept preserved through reconcile ==")
_seed_state({})
sel = {"publishing-studio": {"name": "Publishing Studio", "description": "Author & product dev"}}
sel = bw.reconcile_canonical_floor(sel, {"industry": "publishing", "company_name": "Acme"}, {})
check("publishing-studio" in sel, "custom 'publishing-studio' preserved")
check("marketing" in sel and "billing-finance" in sel, "canonical floor merged in")

print("== R2.3 Capability 2: semantic merge detect + execute ==")
# DETECT: 'Accounting' must be proposed to fold into billing-finance.
_seed_state({})
sel = {
    "accounting": {"name": "Accounting", "description": "bookkeeping, payroll, invoicing"},
    "client-success": {"name": "Client Success", "description": "client success and retention"},
}
# Add the canonical floor so survivors exist.
sel = bw.reconcile_canonical_floor(sel, {"industry": "agency", "company_name": "Acme"}, {})
proposals = bw.detect_semantic_overlaps(sel)
by_custom = {p["custom_id"]: p["target_canonical"] for p in proposals}
check(by_custom.get("accounting") == "billing-finance", f"'accounting' -> billing-finance proposal (got {by_custom.get('accounting')})")
check(by_custom.get("client-success") == "customer-support", f"'client-success' -> customer-support proposal (got {by_custom.get('client-success')})")

# EXECUTE merge: record a 'merge' decision for accounting, 'keep' for client-success.
_seed_state({"canonicalReconciliation": {"mergeDecisions": {"accounting": "merge", "client-success": "keep"}}})
sel2 = {
    "accounting": {"name": "Accounting", "description": "bookkeeping, payroll, invoicing"},
    "client-success": {"name": "Client Success", "description": "client success and retention"},
}
sel2 = bw.reconcile_canonical_floor(sel2, {"industry": "agency", "company_name": "Acme"}, {})
sel2 = bw.apply_semantic_merges(sel2, {"industry": "agency", "company_name": "Acme"})
check("accounting" not in sel2, "'accounting' DROPPED after confirmed merge (no duplicate ships)")
check("billing-finance" in sel2, "billing-finance survivor present after merge")
check("accounting" in (sel2.get("billing-finance", {}).get("mergedFrom") or []),
      "billing-finance records mergedFrom=['accounting']")
check("client-success" in sel2, "'client-success' KEPT standalone (owner chose keep)")
st = _read_state()
sm = st.get("canonicalReconciliation", {}).get("semanticMerges", {})
check(any(m["custom_id"] == "accounting" for m in sm.get("merged", [])), "semanticMerges.merged records accounting")
check("billing-finance" in (st.get("canonicalReconciliation", {}).get("mergedInto", {})),
      "mergedInto carries billing-finance absorption record")

# NO decision -> stays standalone + PENDING (never silent merge).
_seed_state({})
sel3 = {"accounting": {"name": "Accounting", "description": "bookkeeping"}}
sel3 = bw.reconcile_canonical_floor(sel3, {"industry": "agency", "company_name": "Acme"}, {})
sel3 = bw.apply_semantic_merges(sel3, {"industry": "agency", "company_name": "Acme"})
check("accounting" in sel3, "no decision -> 'accounting' stays standalone (no silent merge)")
st3 = _read_state()
pend = st3.get("canonicalReconciliation", {}).get("semanticMerges", {}).get("pending", [])
check(any(p["custom_id"] == "accounting" for p in pend), "undecided overlap recorded PENDING")

print("== R2.4 Capability 3: per-dept custom roles materialized ==")
_seed_state({})
bw.DEPARTMENTS_DIR = tempfile.mkdtemp()
os.makedirs(os.path.join(bw.DEPARTMENTS_DIR, "marketing"), exist_ok=True)
dept_info = {"name": "Marketing", "emoji": "\U0001f4e3", "description": "x"}
dcfg = {"customRoles": ["Influencer Partnerships Lead", {"title": "Newsletter Editor", "summary": "owns the weekly", "permanent": True}]}
created = bw.materialize_custom_roles("marketing", dept_info, dcfg, {"company_name": "Acme", "industry": "coaching"})
check(len(created) == 2, f"2 custom roles materialized (got {len(created)})")
names = sorted(os.listdir(os.path.join(bw.DEPARTMENTS_DIR, "marketing")))
check(any("influencer-partnerships-lead" in n for n in names), "influencer role folder created")
check(any("newsletter-editor" in n for n in names), "newsletter role folder created")
# idempotent re-run: no new folders.
created2 = bw.materialize_custom_roles("marketing", dept_info, dcfg, {"company_name": "Acme", "industry": "coaching"})
check(len(created2) == 0, "re-run materializes 0 (idempotent)")

print("== R2.5 Capability 4: per-dept custom SOPs captured, boundary-aware ==")
_seed_state({})
os.makedirs(os.path.join(bw.DEPARTMENTS_DIR, "billing-finance"), exist_ok=True)
# canonical dept -> overlay (no LLM authoring invited)
dcfg_c = {"customSops": [{"title": "Our refund flow", "procedure": "Step 1 verify; Step 2 refund within 24h."}]}
p = bw.capture_custom_sops("billing-finance", {"name": "Billing & Finance", "emoji": "\U0001f4b3"}, dcfg_c, {"company_name": "Acme"})
check(bool(p) and os.path.isfile(p), "owner-procedures.md written for canonical dept")
body = open(p).read()
check("CANONICAL" in body and "REFUSED" in body, "canonical SOP capture marked as overlay (authoring refused)")
st5 = _read_state()
cap = st5.get("canonicalReconciliation", {}).get("customSopsCaptured", [])
check(any(c.get("isCanonical") is True for c in cap), "build-state records isCanonical=true for billing-finance procedure")
# custom dept -> authoring source
_seed_state({})
os.makedirs(os.path.join(bw.DEPARTMENTS_DIR, "school-of-ai"), exist_ok=True)
p2 = bw.capture_custom_sops("school-of-ai", {"name": "School of AI", "emoji": "\U0001f393"},
                            {"customSops": ["Cohort onboarding: send welcome, grant LMS access, schedule kickoff."]},
                            {"company_name": "Acme"})
body2 = open(p2).read()
check("CUSTOM" in body2 and "LLM-author" in body2, "custom SOP capture marked as authoring source")

print("== R2.6 Capability 5: universal-primary vertical opt-out honored (provenanced) ==")
# Decline 'scheduling-dispatch' (service-industry universal primary) and prove it is skipped.
# Provenance gate (v10.16.26+): bare string 'no' is only honored with ownerDeclineConfirmed=true.
# Use ownerDeclineConfirmed=true + bare string (backward-compat provenanced form).
_seed_state({"canonicalReconciliation": {"ownerDeclineConfirmed": True, "decisions": {"scheduling-dispatch": "no"}}})
sel6 = {}
sel6 = bw.apply_vertical_packs(sel6, {"industry": "coaching", "company_name": "Acme"})
check("scheduling-dispatch" not in sel6, "declined universal-primary 'scheduling-dispatch' SKIPPED (provenanced)")
check("presentations" in sel6, "non-declined universal-primary 'presentations' still added")
st6 = _read_state()
dv = st6.get("verticalPacks", {}).get("declinedVerticals", [])
check(any(x["id"] == "scheduling-dispatch" for x in dv), "verticalPacks.declinedVerticals records the opt-out")

# Also verify that a bare (unprovenanced) decline does NOT skip the vertical.
_seed_state({"canonicalReconciliation": {"decisions": {"scheduling-dispatch": "no"}}})
sel6b = {}
sel6b = bw.apply_vertical_packs(sel6b, {"industry": "coaching", "company_name": "Acme"})
check("scheduling-dispatch" in sel6b, "unprovenanced bare string 'no' does NOT skip vertical (provenance gate holds)")

print("== CORRECTION: NO Ant Farm fold-in capability in the engine ==")
src = open(os.path.join(SCRIPTS, "build-workforce.py")).read().lower()
check("antfarm" not in src and "ant farm" not in src and "ant-farm" not in src,
      "build-workforce.py contains NO ant-farm fold-in (Trevor-only, never a fleet capability)")
check(not os.path.isfile(os.path.join(SCRIPTS, "antfarm-foldin.py")),
      "no scripts/antfarm-foldin.py authored (correction honored)")

print()
if fail:
    print("RESULT: FAIL")
    sys.exit(1)
print("RESULT: PASS")
PY
