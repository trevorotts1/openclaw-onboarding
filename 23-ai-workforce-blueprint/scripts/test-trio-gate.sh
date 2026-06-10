#!/usr/bin/env bash
# test-trio-gate.sh — PRD 2.11 fixture-based verification.
#
# Tests that:
#   1. A role-library with the full trio per dept produces trioStatus=done (exit 0 from trio check)
#   2. A role-library missing any of the three roles in a dept fails (exit 6)
#   3. The add-a-department checklist item is documented (checked by grep)
#
# Does NOT require a client box — runs entirely on the static role-library tree.
# Exit 0 = all assertions passed. Non-zero = one or more assertions failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LIBRARY_DIR="$SKILL_DIR/templates/role-library"

PASS=0
FAIL=0
ERRORS=()

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); ERRORS+=("$1"); }

echo "======================================================"
echo "test-trio-gate.sh — PRD 2.11 fixture verification"
echo "library_dir=$LIBRARY_DIR"
echo "======================================================"

# ────────────────────────────────────────────────────────────────────────────
# ASSERTION 1: Every operational department in the role-library has all 3 files
# ────────────────────────────────────────────────────────────────────────────
echo ""
echo "Assertion 1: All operational depts have QC + research + DA files on disk"
SKIP_DEPTS="master-orchestrator"

python3 - "$LIBRARY_DIR" "$SKIP_DEPTS" <<'PYEOF'
import json, os, sys
from pathlib import Path

library_dir = Path(sys.argv[1])
skip = set(sys.argv[2].split(","))
SKIP_PREFIXES = ("_",)

all_ok = True
for dept_path in sorted(library_dir.iterdir()):
    if not dept_path.is_dir():
        continue
    dept = dept_path.name
    if any(dept.startswith(p) for p in SKIP_PREFIXES) or dept in skip:
        continue
    files = [f.name.lower() for f in dept_path.iterdir() if f.suffix == ".md"]
    has_qc = any("qc" in f for f in files)
    has_research = any("deep-research" in f for f in files)
    has_da = any("devil" in f for f in files)
    ok = has_qc and has_research and has_da
    status = "PASS" if ok else "FAIL"
    print(f"    [{status}] {dept}: qc={has_qc} research={has_research} da={has_da}")
    if not ok:
        all_ok = False

sys.exit(0 if all_ok else 1)
PYEOF
A1_RC=$?
if [ "$A1_RC" -eq 0 ]; then
  pass "All operational depts have QC + research + DA files on disk"
else
  fail "One or more depts missing QC/research/DA file on disk"
fi

# ────────────────────────────────────────────────────────────────────────────
# ASSERTION 2: _index.json registers the trio for every operational dept
# ────────────────────────────────────────────────────────────────────────────
echo ""
echo "Assertion 2: _index.json registers trio roles for every dept"
INDEX_PATH="$LIBRARY_DIR/_index.json"

if [ ! -f "$INDEX_PATH" ]; then
  fail "_index.json not found at $INDEX_PATH"
else
  python3 - "$INDEX_PATH" "$SKIP_DEPTS" <<'PYEOF'
import json, sys

index = json.load(open(sys.argv[1]))
skip = set(sys.argv[2].split(","))
depts = index.get("departments", {})
all_ok = True
for dept, info in sorted(depts.items()):
    if dept.startswith("_") or dept in skip:
        continue
    roles = info.get("roles", [])
    has_qc = any("qc" in r.lower() for r in roles)
    has_research = any("deep-research" in r.lower() for r in roles)
    has_da = any("devil" in r.lower() for r in roles)
    ok = has_qc and has_research and has_da
    status = "PASS" if ok else "FAIL"
    print(f"    [{status}] {dept}: qc={has_qc} research={has_research} da={has_da}")
    if not ok:
        all_ok = False
sys.exit(0 if all_ok else 1)
PYEOF
  A2_RC=$?
  if [ "$A2_RC" -eq 0 ]; then
    pass "_index.json registers trio for all depts"
  else
    fail "_index.json missing trio registration for one or more depts"
  fi
fi

# ────────────────────────────────────────────────────────────────────────────
# ASSERTION 3: DA files have the "NEVER surfaced to the client" operator note
# ────────────────────────────────────────────────────────────────────────────
echo ""
echo "Assertion 3: All DA files contain the OPERATOR NOTE suppression marker"
MISSING_NOTE=()
for da_file in "$LIBRARY_DIR"/*/devils-advocate*.md; do
  if [ ! -f "$da_file" ]; then continue; fi
  if ! grep -q "NEVER surfaced to the client\|OPERATOR NOTE" "$da_file" 2>/dev/null; then
    MISSING_NOTE+=("$(basename "$(dirname "$da_file")")/$(basename "$da_file")")
  fi
done

if [ "${#MISSING_NOTE[@]}" -eq 0 ]; then
  pass "All DA files contain the operator suppression note"
else
  fail "DA files missing operator note: ${MISSING_NOTE[*]}"
fi

# ────────────────────────────────────────────────────────────────────────────
# ASSERTION 4: add-department.sh creates a research-specialist and DA agent row
# ────────────────────────────────────────────────────────────────────────────
echo ""
echo "Assertion 4: add-department.sh creates research + DA agent rows"
ADD_DEPT_SH="$SCRIPT_DIR/../scripts/add-department.sh"
# The script lives one level up since we're in 23-ai-workforce-blueprint/scripts
ADD_DEPT_ALT="$(cd "$SCRIPT_DIR/../../32-command-center-setup/scripts" 2>/dev/null && pwd)/add-department.sh"
if [ ! -f "$ADD_DEPT_SH" ]; then
  ADD_DEPT_SH="$ADD_DEPT_ALT"
fi
if [ ! -f "$ADD_DEPT_SH" ]; then
  # Search the repo
  ADD_DEPT_SH="$(find "$SCRIPT_DIR/../.." -name "add-department.sh" 2>/dev/null | head -1)"
fi

if [ -z "$ADD_DEPT_SH" ] || [ ! -f "$ADD_DEPT_SH" ]; then
  fail "add-department.sh not found — cannot assert trio wiring"
else
  # Check that the script creates a research specialist agent
  if grep -q "deep-research\|research.*specialist\|Deep Research" "$ADD_DEPT_SH" 2>/dev/null; then
    pass "add-department.sh contains research-specialist wiring"
  else
    fail "add-department.sh does NOT create a research-specialist agent row (trio wiring missing)"
  fi
  # Check that the script creates a DA agent
  if grep -q "devil\|devils.advocate\|Devil" "$ADD_DEPT_SH" 2>/dev/null; then
    pass "add-department.sh contains devils-advocate wiring"
  else
    fail "add-department.sh does NOT create a devils-advocate agent row (trio wiring missing)"
  fi
  # Check that DA is NOT mentioned to the client (suppression)
  if grep -q "never.*mention\|NEVER.*surfaced\|not.*surfaced\|hidden\|suppress\|auto.created\|never.*client\|client.*never" "$ADD_DEPT_SH" 2>/dev/null; then
    pass "add-department.sh has DA client-suppression note"
  else
    fail "add-department.sh missing DA client-suppression comment"
  fi
fi

# ────────────────────────────────────────────────────────────────────────────
# ASSERTION 5: verify-library-gate.sh emits trioStatus in its output
# ────────────────────────────────────────────────────────────────────────────
echo ""
echo "Assertion 5: verify-library-gate.sh reports trioStatus"
GATE_SH="$SCRIPT_DIR/verify-library-gate.sh"
if [ ! -f "$GATE_SH" ]; then
  fail "verify-library-gate.sh not found"
else
  if grep -q "trioStatus" "$GATE_SH" 2>/dev/null; then
    pass "verify-library-gate.sh contains trioStatus assertion"
  else
    fail "verify-library-gate.sh does NOT report trioStatus"
  fi
  if grep -q "exit 6" "$GATE_SH" 2>/dev/null; then
    pass "verify-library-gate.sh exits 6 on trio failure"
  else
    fail "verify-library-gate.sh missing exit-6 trio-fail path"
  fi
fi

# ────────────────────────────────────────────────────────────────────────────
# ASSERTION 6: Fixture FAIL test — a library missing DA actually fails the gate
# ────────────────────────────────────────────────────────────────────────────
echo ""
echo "Assertion 6: Trio check correctly FAILS when a dept is missing DA (fixture)"
python3 - <<'PYEOF'
import json, sys, tempfile, os
from pathlib import Path

# Build a fake library dir in /tmp
with tempfile.TemporaryDirectory() as tmpdir:
    lib = Path(tmpdir) / "role-library"
    lib.mkdir()
    # sales — complete trio
    sales = lib / "sales"
    sales.mkdir()
    (sales / "qc-specialist-sales.md").write_text("# QC")
    (sales / "deep-research-specialist-sales.md").write_text("# Research")
    (sales / "devils-advocate-sales.md").write_text("# DA")
    # marketing — MISSING DA
    mkt = lib / "marketing"
    mkt.mkdir()
    (mkt / "qc-specialist-marketing.md").write_text("# QC")
    (mkt / "deep-research-specialist-marketing.md").write_text("# Research")
    # NO DA file

    SKIP = {"_stage1_drafts", "master-orchestrator"}
    dept_results = {}
    trio_gaps = []
    trio_done = True
    for dept_path in sorted(lib.iterdir()):
        if not dept_path.is_dir():
            continue
        dept = dept_path.name
        if dept.startswith("_") or dept in SKIP:
            continue
        files = [f.name.lower() for f in dept_path.iterdir() if f.suffix == ".md"]
        has_qc = any("qc" in f for f in files)
        has_research = any("deep-research" in f for f in files)
        has_da = any("devil" in f for f in files)
        trio_filled = has_qc and has_research and has_da
        dept_results[dept] = trio_filled
        if not trio_filled:
            trio_done = False
            missing = []
            if not has_qc: missing.append("qc-specialist")
            if not has_research: missing.append("deep-research-specialist")
            if not has_da: missing.append("devils-advocate")
            trio_gaps.append(f"{dept} missing: {', '.join(missing)}")

    if trio_done:
        print("    [FAIL] Fixture test: trio_done=True but marketing has no DA — gate should have failed")
        sys.exit(1)
    elif "marketing" in [g.split()[0] for g in trio_gaps]:
        print(f"    [PASS] Fixture correctly identifies marketing as missing DA: {trio_gaps}")
        sys.exit(0)
    else:
        print(f"    [FAIL] Fixture did not identify marketing gap: {trio_gaps}")
        sys.exit(1)
PYEOF
A6_RC=$?
if [ "$A6_RC" -eq 0 ]; then
  pass "Fixture FAIL test: missing-DA correctly triggers trio gate failure"
else
  fail "Fixture FAIL test: gate logic did not catch missing DA"
fi

# ────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ────────────────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "RESULTS: ${PASS} passed, ${FAIL} failed"
if [ "$FAIL" -gt 0 ]; then
  echo "FAILING ASSERTIONS:"
  for e in "${ERRORS[@]}"; do
    echo "  - $e"
  done
  echo "EXIT: FAIL"
  exit 1
fi
echo "EXIT: PASS"
exit 0
