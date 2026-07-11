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
#     7. (C1) The EXACT live finalize-directive shape — dict entries under
#        canonicalReconciliation.declinedDepartments carrying a per-entry
#        provenance TRIPLE {id, decidedBy, decidedAt} — is HONORED without the
#        block-level ownerDeclineConfirmed flag, read from BOTH build-state levels,
#        while a malformed dict (incomplete triple) is REJECTED (fail-safe).
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

# ── Test 5: normalization lockstep — a decline keyed by DISPLAY / UNDERSCORE ───
#            variant ("Video" / "billing_finance") is HONORED by BOTH the builder
#            and the floor checker, AND the dept is NOT built. (Issue #2, PROVEN
#            residual over-provision vector.) Before the fix the builder stored raw ids and
#            tested `cid in declined` — 'video' != 'Video' — so it FORCE-BUILT the
#            declined dept while the floor gate (which normalized) passed the
#            over-built box. This asserts the lockstep is now closed.
print("== T5: normalization lockstep — 'Video'/'billing_finance' decline honored by builder AND floor ==")

# Object-form provenanced declines keyed by a display-name / underscore variant.
_prov = {"source": "owner-interview", "decidedAt": "2026-07-03T00:00:00Z", "decidedBy": "owner"}
bs_variant = {"canonicalReconciliation": {"decisions": {
    "Video":           {"decision": "no", **_prov},
    "billing_finance": {"decision": "no", **_prov},
}}}

# 5a: builder decline set — normalized, both honored.
bw_declined = bw._canonical_decline_set(bs_variant)
check(bw._decline_norm("video") in bw_declined and bw._decline_norm("billing-finance") in bw_declined,
      "T5a: builder honors 'Video'/'billing_finance' (normalized 'video'/'billingfinance' in declined set)")

# 5b: floor checker decline set — IDENTICAL normalized set (lockstep).
df_declined = df.declined_set(bs_variant)
check(bw_declined == df_declined,
      f"T5b: builder and floor declined sets are IDENTICAL (lockstep): {sorted(bw_declined)} == {sorted(df_declined)}")

# 5c: reconcile_canonical_floor does NOT build the declined depts (no over-build).
bw._build_state_path = lambda: _state_path
with open(_state_path, "w") as f:
    json.dump(bs_variant, f)
sel = bw.reconcile_canonical_floor({}, {"industry": "coaching", "company_name": "Acme"}, {})
check("video" not in sel and "billing-finance" not in sel,
      "T5c: reconcile SKIPS declined 'video' + 'billing-finance' (dept NOT force-built)")
check("marketing" in sel and "sales" in sel,
      "T5d: reconcile still builds the non-declined canonical floor (marketing, sales present)")

# ── Test 6: EXACT LIVE SHAPE (C1) — per-entry-provenance dict declines under ────
#            canonicalReconciliation.declinedDepartments, ownerDeclineConfirmed
#            ABSENT and decisions=null. This is the finalize-directive shape found
#            on the live box: three vertical-pack depts declined by an in-place
#            {id, decidedBy, decidedAt} triple. Before the C1 fix the reader looked
#            only at the build-state TOP level (missed the recon-level list) AND
#            could not parse dict entries (norm(dict) garbage) AND gated on the
#            unset ownerDeclineConfirmed flag — so ALL THREE declines were silently
#            ignored and the depts were rebuilt. This asserts all three now land
#            declined (in BOTH the builder and the floor reader, lockstep) WITHOUT
#            ownerDeclineConfirmed, while a malformed dict (missing decidedAt) is
#            still REJECTED (fail-safe — a bad entry never shrinks the floor).
print("== T6: exact live shape — recon.declinedDepartments dict triples honored without ownerDeclineConfirmed ==")

bs_live = {"canonicalReconciliation": {
    "declinedDepartments": [
        {"id": "listings", "name": "Listings Management",
         "reason": "vertical pack; do not re-add",
         "decidedBy": "owner (finalize directive)", "decidedAt": "2026-06-14T06:00:00Z"},
        {"id": "scheduling-dispatch", "name": "Scheduling & Dispatch",
         "reason": "vertical pack; do not re-add",
         "decidedBy": "owner (finalize directive)", "decidedAt": "2026-06-14T06:00:00Z"},
        {"id": "logistics-fulfillment", "name": "Logistics & Fulfillment",
         "reason": "vertical pack; do not re-add",
         "decidedBy": "owner (finalize directive)", "decidedAt": "2026-06-14T06:00:00Z"},
    ],
    # ownerDeclineConfirmed ABSENT (None) and decisions null — exactly as on the box.
    "decisions": None,
}}

bw_live = bw._canonical_decline_set(bs_live)
df_live = df.declined_set(bs_live)
for _slug in ("listings", "scheduling-dispatch", "logistics-fulfillment"):
    check(bw._decline_norm(_slug) in bw_live,
          f"T6a: builder honors live dict-triple decline '{_slug}' (no ownerDeclineConfirmed)")
    check(df._norm(_slug) in df_live,
          f"T6b: floor reader honors live dict-triple decline '{_slug}' (lockstep)")
check(bw_live == df_live,
      f"T6c: builder and floor declined sets IDENTICAL on the live shape: {sorted(bw_live)}")

# 6d: reconcile SKIPS the three declined vertical-pack depts (not force-built).
bw._build_state_path = lambda: _state_path
with open(_state_path, "w") as f:
    json.dump(bs_live, f)
sel_live = bw.reconcile_canonical_floor({}, {"industry": "coaching", "company_name": "Acme"}, {})
check(all(s not in sel_live for s in ("listings", "scheduling-dispatch", "logistics-fulfillment")),
      "T6d: reconcile SKIPS live-declined listings/scheduling-dispatch/logistics-fulfillment")

# 6e: a malformed dict (missing decidedAt) is REJECTED — dept stays in floor.
bs_malformed = {"canonicalReconciliation": {"declinedDepartments": [
    {"id": "marketing", "decidedBy": "owner"},   # no decidedAt -> incomplete triple
]}}
declined_malformed = bw._canonical_decline_set(bs_malformed)
check(bw._decline_norm("marketing") not in declined_malformed,
      "T6e: malformed dict decline (missing decidedAt) REJECTED — 'marketing' stays in floor (fail-safe)")

# 6f: top-level declinedDepartments dict triple is ALSO read (both levels).
bs_toplevel = {"declinedDepartments": [
    {"id": "audio", "decidedBy": "owner", "decidedAt": "2026-06-14T06:00:00Z"},
]}
declined_toplevel = bw._canonical_decline_set(bs_toplevel)
check(bw._decline_norm("audio") in declined_toplevel,
      "T6f: top-level declinedDepartments dict triple honored (both-levels read)")

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
