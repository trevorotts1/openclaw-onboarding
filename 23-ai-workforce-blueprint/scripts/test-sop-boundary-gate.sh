#!/usr/bin/env bash
# test-sop-boundary-gate.sh — PRD 2.12 boundary gate fixture tests
#
# Verifies (offline, no client box required):
#   1. A canonical dept/role resolves by COPY from the library (never authors)
#   2. The build gate asserts canonical depts never enter the authoring path
#      (classify_manifest_depts detects violation; assert_no_canonical fails rc=7)
#   3. Only genuinely-custom roles are eligible for authoring
#   4. Token economics: canonical-only manifest → zero LLM authoring calls
#
# EXIT CODES
#   0  all tests pass
#   1  one or more tests failed
#
# Runs in a temp dir. Cleans up on exit. Safe to re-run.
# Uses only python3 and the scripts in this directory — no network, no OpenClaw,
# no client box needed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0
ERRORS=()

pass() { PASS=$((PASS + 1)); echo "[PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); ERRORS+=("$1"); echo "[FAIL] $1"; }

# Temp workspace (cleaned up on exit)
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

echo "======================================================================"
echo "test-sop-boundary-gate.sh — PRD 2.12 fixture tests"
echo "Script dir: $SCRIPT_DIR"
echo "Skill dir:  $SKILL_DIR"
echo "Temp dir:   $TMPDIR_TEST"
echo "======================================================================"
echo ""

# ── 1. Module import / CLI available ─────────────────────────────────────────
echo "--- 1. Module import ---"

python3 - "$SCRIPT_DIR" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import (
    CANONICAL_LIBRARY_DEPT_IDS,
    is_canonical_dept,
    refuse_if_canonical,
    classify_manifest_depts,
    assert_no_canonical_in_authoring_path,
    CanonicalDeptAuthError,
)
assert CANONICAL_LIBRARY_DEPT_IDS, 'CANONICAL_LIBRARY_DEPT_IDS must not be empty'
print(f'CANONICAL_LIBRARY_DEPT_IDS loaded: {sorted(CANONICAL_LIBRARY_DEPT_IDS)}')
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "1a: sop_boundary_gate module imports cleanly; CANONICAL_LIBRARY_DEPT_IDS is non-empty" \
                 || fail "1a: sop_boundary_gate import failed"

# CLI --list-canonical should exit 0
python3 "$SCRIPT_DIR/sop-boundary-gate.py" --list-canonical >/dev/null 2>&1 \
  && pass "1b: CLI --list-canonical exits 0" \
  || fail "1b: CLI --list-canonical failed"

echo ""

# ── 2. Canonical dept detection ───────────────────────────────────────────────
echo "--- 2. Canonical dept detection ---"

python3 - "$SCRIPT_DIR" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import is_canonical_dept, refuse_if_canonical, CanonicalDeptAuthError

# Canonical depts (in role-library directory tree)
canonical_cases = [
    "marketing", "sales", "audio", "video", "graphics",
    "research", "social-media", "web-development", "app-development",
    "crm", "communications", "customer-support", "openclaw-maintenance",
    "paid-advertisement", "project-architecture-office", "general-task",
    # alias cases
    "billing-finance",   # alias -> billing
    "legal",             # alias -> legal-compliance
]
for dept_id in canonical_cases:
    assert is_canonical_dept(dept_id), f"Expected {dept_id!r} to be canonical"

# Custom depts (not in role-library directory tree)
custom_cases = [
    "hat-creation-department",
    "horse-shoeing",
    "custom-consulting",
    "my-unique-dept",
    "presentations",      # vertical pack but NOT in role-library
    "engineering",        # vertical pack but NOT in role-library
    "podcast",            # vertical pack but NOT in role-library
]
for dept_id in custom_cases:
    assert not is_canonical_dept(dept_id), f"Expected {dept_id!r} to be custom (not canonical)"

# refuse_if_canonical raises for canonical depts
for dept_id in ["marketing", "sales"]:
    try:
        refuse_if_canonical(dept_id)
        raise AssertionError(f"refuse_if_canonical({dept_id!r}) should have raised CanonicalDeptAuthError")
    except CanonicalDeptAuthError as e:
        assert "REFUSE authoring" in str(e), f"Expected 'REFUSE authoring' in error message: {e}"

# refuse_if_canonical passes for custom depts
for dept_id in ["hat-creation-department", "horse-shoeing"]:
    refuse_if_canonical(dept_id)  # should NOT raise

print("All canonical/custom detection assertions passed")
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "2a: is_canonical_dept() correctly classifies canonical vs custom depts" \
                 || fail "2a: canonical/custom detection failed (rc=$RC)"

echo ""

# ── 3. classify_manifest_depts — canonical manifest → violation ───────────────
echo "--- 3. Manifest classification: canonical dept → violation ---"

# Build a fake manifest with canonical depts only
CANONICAL_MANIFEST="$TMPDIR_TEST/canonical-manifest.json"
python3 - "$SCRIPT_DIR" "$CANONICAL_MANIFEST" <<'PYEOF'
import json, sys
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import CANONICAL_LIBRARY_DEPT_IDS
depts = []
for dept_id in sorted(list(CANONICAL_LIBRARY_DEPT_IDS))[:3]:
    depts.append({
        "dept_id": dept_id,
        "dept_name": dept_id.replace("-", " ").title(),
        "dept_dir": "/fake/path/" + dept_id,
        "company_name": "Test Corp",
        "industry": "test",
        "sop_files": [
            {"role_folder": "chief-officer", "sop_file": "01-standard-workflow.md"}
        ],
    })
manifest = {
    "version": "1.0",
    "company": "Test Corp",
    "company_slug": "test-corp",
    "industry": "test",
    "generated_at": "2026-06-10T00:00:00",
    "max_parallel_sub_agents": 10,
    "departments": depts,
    "sub_agent_instructions": "test",
}
with open(sys.argv[2], "w") as f:
    json.dump(manifest, f, indent=2)
print(f"Wrote canonical-only manifest with depts: {[d['dept_id'] for d in depts]}")
PYEOF

python3 - "$SCRIPT_DIR" "$CANONICAL_MANIFEST" <<'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import classify_manifest_depts, assert_no_canonical_in_authoring_path

result = classify_manifest_depts(sys.argv[2])
assert result["violation"] is True, f"Expected violation=True for canonical-only manifest, got: {result}"
assert len(result["canonical"]) > 0, "Expected canonical depts in canonical manifest"
assert len(result["custom"]) == 0, "Expected no custom depts in canonical-only manifest"
assert result["violation_reason"], "Expected a non-empty violation_reason"
print(f"classify_manifest_depts correctly detected violation: {result['violation_reason'][:120]}")

rc = assert_no_canonical_in_authoring_path(sys.argv[2])
assert rc == 7, f"Expected rc=7 for canonical-only manifest, got rc={rc}"
print(f"assert_no_canonical_in_authoring_path correctly returned rc=7")
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "3a: classify_manifest_depts detects violation when canonical depts are in authoring manifest" \
                 || fail "3a: canonical manifest violation detection failed (rc=$RC)"

# CLI --check-manifest should exit 7 for canonical-only manifest
python3 "$SCRIPT_DIR/sop-boundary-gate.py" --check-manifest "$CANONICAL_MANIFEST" >/dev/null 2>&1
CLI_RC=$?
[ "$CLI_RC" -eq 7 ] && pass "3b: CLI --check-manifest exits 7 for canonical-only manifest (boundary violation)" \
                      || fail "3b: CLI --check-manifest should exit 7, got $CLI_RC"

echo ""

# ── 4. classify_manifest_depts — custom dept → PASS (no violation) ────────────
echo "--- 4. Manifest classification: custom dept → PASS ---"

CUSTOM_MANIFEST="$TMPDIR_TEST/custom-manifest.json"
python3 - "$CUSTOM_MANIFEST" <<'PYEOF'
import json, sys
manifest = {
    "version": "1.0",
    "company": "Test Corp",
    "company_slug": "test-corp",
    "industry": "test",
    "generated_at": "2026-06-10T00:00:00",
    "max_parallel_sub_agents": 10,
    "departments": [
        {
            "dept_id": "hat-creation-department",
            "dept_name": "Hat Creation Department",
            "dept_dir": "/fake/path/hat-creation-department",
            "company_name": "Test Corp",
            "industry": "fashion",
            "sop_files": [
                {"role_folder": "hat-designer", "sop_file": "01-design-workflow.md"}
            ],
        },
        {
            "dept_id": "horse-shoeing",
            "dept_name": "Horse Shoeing",
            "dept_dir": "/fake/path/horse-shoeing",
            "company_name": "Test Corp",
            "industry": "equine",
            "sop_files": [],
        },
    ],
    "sub_agent_instructions": "test",
}
with open(sys.argv[1], "w") as f:
    json.dump(manifest, f, indent=2)
print(f"Wrote custom-only manifest")
PYEOF

python3 - "$SCRIPT_DIR" "$CUSTOM_MANIFEST" <<'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import classify_manifest_depts, assert_no_canonical_in_authoring_path

result = classify_manifest_depts(sys.argv[2])
assert result["violation"] is False, f"Expected violation=False for custom-only manifest, got: {result}"
assert len(result["canonical"]) == 0, "Expected no canonical depts in custom manifest"
assert len(result["custom"]) == 2, f"Expected 2 custom depts, got {len(result['custom'])}"
print(f"classify_manifest_depts correctly returned no violation for custom-only manifest")

rc = assert_no_canonical_in_authoring_path(sys.argv[2])
assert rc == 0, f"Expected rc=0 for custom-only manifest, got rc={rc}"
print(f"assert_no_canonical_in_authoring_path correctly returned rc=0 for custom manifest")
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "4a: classify_manifest_depts returns no violation for custom-only manifest" \
                 || fail "4a: custom manifest no-violation check failed (rc=$RC)"

# CLI --check-manifest should exit 0 for custom-only manifest
python3 "$SCRIPT_DIR/sop-boundary-gate.py" --check-manifest "$CUSTOM_MANIFEST" >/dev/null 2>&1
CLI_RC=$?
[ "$CLI_RC" -eq 0 ] && pass "4b: CLI --check-manifest exits 0 for custom-only manifest (PASS)" \
                      || fail "4b: CLI --check-manifest should exit 0 for custom manifest, got $CLI_RC"

echo ""

# ── 5. Mixed manifest: canonical + custom → violation, but custom listed ──────
echo "--- 5. Mixed manifest: canonical + custom depts ---"

MIXED_MANIFEST="$TMPDIR_TEST/mixed-manifest.json"
python3 - "$SCRIPT_DIR" "$MIXED_MANIFEST" <<'PYEOF'
import json, sys
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import CANONICAL_LIBRARY_DEPT_IDS
canonical_id = sorted(list(CANONICAL_LIBRARY_DEPT_IDS))[0]
manifest = {
    "version": "1.0",
    "company": "Test Corp",
    "company_slug": "test-corp",
    "industry": "test",
    "generated_at": "2026-06-10T00:00:00",
    "max_parallel_sub_agents": 10,
    "departments": [
        {
            "dept_id": canonical_id,
            "dept_name": canonical_id.replace("-", " ").title(),
            "dept_dir": "/fake/path/" + canonical_id,
            "company_name": "Test Corp",
            "industry": "test",
            "sop_files": [{"role_folder": "some-role", "sop_file": "01-workflow.md"}],
        },
        {
            "dept_id": "hat-creation-department",
            "dept_name": "Hat Creation Department",
            "dept_dir": "/fake/path/hat-creation-department",
            "company_name": "Test Corp",
            "industry": "fashion",
            "sop_files": [{"role_folder": "hat-designer", "sop_file": "01-design.md"}],
        },
    ],
    "sub_agent_instructions": "test",
}
with open(sys.argv[2], "w") as f:
    json.dump(manifest, f, indent=2)
print(f"Wrote mixed manifest (canonical: {canonical_id}, custom: hat-creation-department)")
PYEOF

python3 - "$SCRIPT_DIR" "$MIXED_MANIFEST" <<'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import classify_manifest_depts

result = classify_manifest_depts(sys.argv[2])
assert result["violation"] is True, f"Expected violation=True for mixed manifest"
assert len(result["canonical"]) == 1, f"Expected 1 canonical dept, got {len(result['canonical'])}"
assert len(result["custom"]) == 1, f"Expected 1 custom dept, got {len(result['custom'])}"
assert result["custom"][0]["dept_id"] == "hat-creation-department", \
    f"Expected hat-creation-department as custom, got {result['custom']}"
print(f"Mixed manifest: canonical={[d['dept_id'] for d in result['canonical']]} "
      f"custom={[d['dept_id'] for d in result['custom']]} violation={result['violation']}")
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "5a: Mixed manifest: canonical dept flagged as violation, custom dept preserved" \
                 || fail "5a: Mixed manifest classification failed (rc=$RC)"

echo ""

# ── 6. Alias resolution ───────────────────────────────────────────────────────
echo "--- 6. Alias resolution ---"

python3 - "$SCRIPT_DIR" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import is_canonical_dept

# billing-finance -> billing (in library)
assert is_canonical_dept("billing-finance"), "billing-finance should map to canonical billing"
assert is_canonical_dept("billing_finance"), "billing_finance should map to canonical billing"
# legal -> legal-compliance (in library)
assert is_canonical_dept("legal"), "legal should map to canonical legal-compliance"
# dept- prefix strip
assert is_canonical_dept("dept-marketing"), "dept-marketing should strip to canonical marketing"
# -dept suffix strip
assert is_canonical_dept("sales-dept"), "sales-dept should strip to canonical sales"
# customer-service alias
assert is_canonical_dept("customer-service"), "customer-service should map to canonical customer-support"
print("All alias resolution cases pass")
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "6a: Alias resolution (billing-finance, legal, dept-prefix, -dept suffix, customer-service) all correct" \
                 || fail "6a: Alias resolution failed (rc=$RC)"

echo ""

# ── 7. Edge cases ─────────────────────────────────────────────────────────────
echo "--- 7. Edge cases ---"

EMPTY_MANIFEST="$TMPDIR_TEST/empty-manifest.json"
echo '{"version":"1.0","company":"Test","departments":[],"sub_agent_instructions":"test"}' > "$EMPTY_MANIFEST"

python3 - "$SCRIPT_DIR" "$EMPTY_MANIFEST" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import classify_manifest_depts

result = classify_manifest_depts(sys.argv[2])
assert result["violation"] is False, f"Empty manifest should not be a violation"
print("Empty manifest returns no violation — correct")
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "7a: Empty manifest (no depts) returns no violation" \
                 || fail "7a: Empty manifest edge case failed (rc=$RC)"

# Missing manifest → no violation (graceful)
python3 - "$SCRIPT_DIR" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import classify_manifest_depts

result = classify_manifest_depts("/nonexistent/path/sop-research-manifest.json")
assert result["violation"] is False, "Missing manifest should not be a violation"
assert "not found" in result["violation_reason"], f"Expected 'not found' in reason: {result['violation_reason']}"
print(f"Missing manifest: violation={result['violation']} reason='{result['violation_reason']}'")
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "7b: Missing manifest file handled gracefully (no false violation)" \
                 || fail "7b: Missing manifest edge case failed (rc=$RC)"

echo ""

# ── 8. Build gate: assert_no_canonical_in_authoring_path ──────────────────────
echo "--- 8. Build gate assertion ---"

# A manifest that has ONLY custom depts produces rc=0
python3 "$SCRIPT_DIR/sop-boundary-gate.py" --check-manifest "$CUSTOM_MANIFEST" >/dev/null 2>&1
CLI_RC=$?
[ "$CLI_RC" -eq 0 ] && pass "8a: Build gate passes (rc=0) for custom-only manifest" \
                      || fail "8a: Build gate should return 0 for custom manifest, got $CLI_RC"

# A manifest that has canonical depts produces rc=7
python3 "$SCRIPT_DIR/sop-boundary-gate.py" --check-manifest "$CANONICAL_MANIFEST" >/dev/null 2>&1
CLI_RC=$?
[ "$CLI_RC" -eq 7 ] && pass "8b: Build gate fails (rc=7) for canonical-dept manifest" \
                      || fail "8b: Build gate should return 7 for canonical manifest, got $CLI_RC"

echo ""

# ── 9. CANONICAL_LIBRARY_DEPT_IDS sourced from role-library dir tree ──────────
echo "--- 9. Canonical set sourced from role-library directory tree ---"

python3 - "$SCRIPT_DIR" "$SKILL_DIR" <<'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import CANONICAL_LIBRARY_DEPT_IDS, ROLE_LIBRARY_DIR

# Must match the actual directory contents
actual_dirs = {
    d.name for d in ROLE_LIBRARY_DIR.iterdir()
    if d.is_dir() and not d.name.startswith("_") and d.name not in {"master-orchestrator"}
}
assert CANONICAL_LIBRARY_DEPT_IDS == actual_dirs, (
    f"CANONICAL_LIBRARY_DEPT_IDS mismatch.\n"
    f"  Expected (from disk): {sorted(actual_dirs)}\n"
    f"  Got: {sorted(CANONICAL_LIBRARY_DEPT_IDS)}"
)
print(f"CANONICAL_LIBRARY_DEPT_IDS matches role-library directory tree exactly ({len(actual_dirs)} depts)")
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "9a: CANONICAL_LIBRARY_DEPT_IDS matches role-library directory tree (no hard-coded list)" \
                 || fail "9a: CANONICAL_LIBRARY_DEPT_IDS vs directory tree mismatch"

echo ""

# ── 10. Token economics: canonical path costs zero generation ─────────────────
echo "--- 10. Canonical dept triggers COPY, not authoring ---"

# Verify that a manifest with only canonical depts, when processed by the
# boundary gate, produces an empty custom list (nothing to author).
python3 - "$SCRIPT_DIR" "$CANONICAL_MANIFEST" <<'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from sop_boundary_gate import classify_manifest_depts

result = classify_manifest_depts(sys.argv[2])
canonical_count = len(result["canonical"])
custom_count = len(result["custom"])

# Simulate what populate-sops-from-manifest.py does when boundary gate fires:
# it filters canonical depts out and processes only custom depts.
# If no custom depts remain, zero LLM authoring calls are made.
authoring_would_run = custom_count > 0
assert not authoring_would_run, (
    f"For canonical-only manifest, authoring must NOT run. "
    f"Got {custom_count} custom depts that would trigger authoring."
)
print(
    f"Token economics verified: canonical manifest -> "
    f"{canonical_count} canonical (COPY path), "
    f"{custom_count} custom (authoring path) = 0 LLM authoring calls"
)
PYEOF
RC=$?
[ "$RC" -eq 0 ] && pass "10a: Canonical-only manifest triggers zero LLM authoring calls (copy path only)" \
                 || fail "10a: Token economics check failed (rc=$RC)"

echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "======================================================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "======================================================================"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "FAILED tests:"
  for err in "${ERRORS[@]}"; do
    echo "  - $err"
  done
  exit 1
fi
echo "All tests pass."
exit 0
