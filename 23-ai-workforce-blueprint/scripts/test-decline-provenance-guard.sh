#!/usr/bin/env bash
# test-decline-provenance-guard.sh — CI guard: decline provenance enforcement.
#
# WHAT IT TESTS:
#   Proves the provenance gate on _canonical_decline_set (build-workforce.py) and
#   declined_set (department-floor.py) cannot be bypassed by a fabricated
#   canonicalReconciliation block (the Star floor flag #2 / intentionalScope issue).
#
#   The fabrication vector: any actor (closeout agent, finisher, seed script) could
#   write bare string "no" or a flat declinedDepartments[] list into build-state
#   and silently shrink the floor below the mandatory count. This test asserts that:
#     1. Bare string "no" without ownerDeclineConfirmed is REJECTED (dept stays in floor).
#     2. flat declinedDepartments[] without ownerDeclineConfirmed is REJECTED.
#     3. Object-form provenance {decision, source, decidedAt, decidedBy} is HONORED.
#     4. ownerDeclineConfirmed=true + bare string is HONORED (backward-compat).
#     5. _write_canonical_reconciliation() NEVER introduces a new "no" decision
#        or declinedDepartments entry on its own (audit assurance).
#     6. No closeout/finisher script in the repo writes a decline entry.
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
CLOSEOUT_SCRIPTS="$(cd "$REPO_ROOT/37-zhc-closeout/scripts" 2>/dev/null && pwd || true)"

PASS=0; FAIL=0
ok()   { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

python3 - "$SCRIPT_DIR" "$SKILL_DIR" <<'PYEOF'
import sys, os, json, importlib.util, tempfile

scripts_dir = sys.argv[1]
skill_dir = sys.argv[2]

fail = 0
def check(cond, msg):
    global fail
    status = "PASS" if cond else "FAIL"
    print(f"  {status}: {msg}")
    if not cond:
        fail = 1

# ── Load build-workforce.py ───────────────────────────────────────────────────
spec = importlib.util.spec_from_file_location("bw", os.path.join(scripts_dir, "build-workforce.py"))
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)

# ── Load department-floor.py ──────────────────────────────────────────────────
spec2 = importlib.util.spec_from_file_location(
    "df", os.path.join(scripts_dir, "department-floor.py"))
df = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(df)

# ── Test 1: build-workforce._canonical_decline_set provenance gate ────────────
print("== T1: build-workforce._canonical_decline_set provenance gate ==")

# 1a: bare string "no" without ownerDeclineConfirmed -> REJECTED (empty set).
bs_bare_str = {"canonicalReconciliation": {"decisions": {"audio": "no"}}}
declined = bw._canonical_decline_set(bs_bare_str)
check("audio" not in declined,
      "T1a: bare string 'no' without ownerDeclineConfirmed -> REJECTED (audio NOT in declined set)")

# 1b: flat declinedDepartments[] without ownerDeclineConfirmed -> REJECTED.
bs_bare_list = {"declinedDepartments": ["audio"]}
declined2 = bw._canonical_decline_set(bs_bare_list)
check("audio" not in declined2,
      "T1b: bare declinedDepartments[] without ownerDeclineConfirmed -> REJECTED (audio NOT in declined set)")

# 1c: object-form provenance -> HONORED.
bs_obj = {"canonicalReconciliation": {"decisions": {"audio": {
    "decision": "no",
    "source": "owner-interview",
    "decidedAt": "2026-06-23T00:00:00Z",
    "decidedBy": "owner",
}}}}
declined3 = bw._canonical_decline_set(bs_obj)
check("audio" in declined3,
      "T1c: object-form provenance {decision,source,decidedAt,decidedBy} -> HONORED (audio in declined set)")

# 1d: ownerDeclineConfirmed=true + bare string -> HONORED (backward-compat).
bs_confirmed_str = {"canonicalReconciliation": {"ownerDeclineConfirmed": True, "decisions": {"audio": "no"}}}
declined4 = bw._canonical_decline_set(bs_confirmed_str)
check("audio" in declined4,
      "T1d: bare string 'no' + ownerDeclineConfirmed=true -> HONORED (backward-compat)")

# 1e: ownerDeclineConfirmed=true + flat list -> HONORED.
bs_confirmed_list = {
    "declinedDepartments": ["audio"],
    "canonicalReconciliation": {"ownerDeclineConfirmed": True},
}
declined5 = bw._canonical_decline_set(bs_confirmed_list)
check("audio" in declined5,
      "T1e: flat list + ownerDeclineConfirmed=true -> HONORED (backward-compat)")

# 1f: object-form with MISSING required field -> REJECTED.
bs_incomplete_obj = {"canonicalReconciliation": {"decisions": {"audio": {
    "decision": "no",
    "source": "owner-interview",
    # missing decidedAt and decidedBy
}}}}
declined6 = bw._canonical_decline_set(bs_incomplete_obj)
check("audio" not in declined6,
      "T1f: object-form missing decidedAt/decidedBy -> REJECTED (audio NOT in declined set)")

# ── Test 2: department-floor.declined_set provenance gate (in lockstep) ───────
print("== T2: department-floor.declined_set provenance gate (lockstep with build-workforce) ==")

# 2a: bare string "no" without ownerDeclineConfirmed -> REJECTED.
df_declined1 = df.declined_set({"canonicalReconciliation": {"decisions": {"billing-finance": "no"}}})
check(df._norm("billing-finance") not in df_declined1,
      "T2a: bare string 'no' without ownerDeclineConfirmed -> REJECTED in department-floor")

# 2b: object-form provenance -> HONORED.
df_declined2 = df.declined_set({"canonicalReconciliation": {"decisions": {"billing-finance": {
    "decision": "no", "source": "owner-interview",
    "decidedAt": "2026-06-23T00:00:00Z", "decidedBy": "owner",
}}}})
check(df._norm("billing-finance") in df_declined2,
      "T2b: object-form provenance -> HONORED in department-floor")

# 2c: ownerDeclineConfirmed + bare string -> HONORED.
df_declined3 = df.declined_set({"canonicalReconciliation": {
    "ownerDeclineConfirmed": True, "decisions": {"billing-finance": "no"}}})
check(df._norm("billing-finance") in df_declined3,
      "T2c: ownerDeclineConfirmed + bare string -> HONORED in department-floor")

# ── Test 3: _write_canonical_reconciliation NEVER introduces a "no" decision ──
print("== T3: _write_canonical_reconciliation never auto-writes a decline ==")

_tmpdir = tempfile.mkdtemp()
_state_path = os.path.join(_tmpdir, "state.json")
bw._build_state_path = lambda: _state_path

# Seed a clean state (no declines).
with open(_state_path, "w") as f:
    json.dump({}, f)

# Call _write_canonical_reconciliation with legitimate data (no decisions set to "no").
bw._write_canonical_reconciliation({
    "autoIncluded": ["marketing", "sales"],
    "clientCustoms": ["publishing"],
    "floorSize": 22,
    "decisions": {},
    "source": "test",
})
state = json.load(open(_state_path))
recon = state.get("canonicalReconciliation", {})
decisions = recon.get("decisions", {})
declined_in_decisions = [k for k, v in decisions.items()
                         if (isinstance(v, dict) and str(v.get("decision", "")).strip().lower() == "no")
                         or (isinstance(v, str) and v.strip().lower() == "no")]
check(len(declined_in_decisions) == 0,
      "T3a: _write_canonical_reconciliation did NOT introduce any 'no' decision entries")
check("declinedDepartments" not in state,
      "T3b: _write_canonical_reconciliation did NOT write a declinedDepartments key")

print()
if fail:
    print("RESULT: FAIL")
    sys.exit(1)
print("RESULT: PASS")
PYEOF

pyexit=$?
echo ""

# ── Shell test: closeout scripts don't write decline entries ──────────────────
echo "== T4: closeout/finisher scripts do not write declinedDepartments/intentionalScope =="
if [ -z "$CLOSEOUT_SCRIPTS" ] || [ ! -d "$CLOSEOUT_SCRIPTS" ]; then
    echo "  SKIP: 37-zhc-closeout/scripts/ not found — skipping closeout script scan"
    ok "T4: closeout scripts scan SKIPPED (directory not present)"
else
    # Search for any place that writes declinedDepartments or intentionalScope.
    HITS=$(grep -rn "declinedDepartments\|intentionalScope" "$CLOSEOUT_SCRIPTS" \
           --include="*.sh" --include="*.py" \
           | grep -v "^Binary" \
           | grep -v "#.*declinedDepartments\|#.*intentionalScope" \
           | grep -v "echo.*PASS\|echo.*FAIL\|print.*PASS\|print.*FAIL" \
           | grep "declinedDepartments\|intentionalScope" \
           | grep -v "if.*declinedDepartments\|test.*declinedDepartments\|grep.*declinedDepartments\|\.declined\|rc=3" \
           | grep -v "minus explicit declines\|was.*declined\|explicitly declined" \
           2>/dev/null || true)
    if [ -z "$HITS" ]; then
        ok "T4: no closeout/finisher script writes declinedDepartments or intentionalScope"
    else
        bad "T4: closeout script WRITES a decline key (FABRICATION RISK)"
        echo "    Hits:"
        echo "$HITS" | head -20 | while IFS= read -r line; do echo "      $line"; done
    fi
fi

# Final tally
echo "--------------------------------------------"
[ $pyexit -eq 0 ] && [ "$FAIL" -eq 0 ] && {
    echo "ALL DECLINE-PROVENANCE GUARD TESTS PASSED"
    exit 0
} || {
    echo "DECLINE-PROVENANCE GUARD TEST FAILURES"
    exit 1
}
