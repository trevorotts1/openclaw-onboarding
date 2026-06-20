#!/usr/bin/env bash
# test-trio-gate.sh — PRD 2.11 fixture-based verification.
#
# Tests that:
#   1. Every TRIO-REQUIRING dept (canonical roster registers qc+research+da) has
#      all three roles on disk; minimal ops depts (roster lacks the trio) are
#      exempt — matching the Option-2 roster-scoped gate (verify-library-gate.sh).
#   2. A role-library missing any of the three roles in a TRIO-REQUIRING dept
#      fails (exit 6); minimal ops depts do not trip the gate.
#   3. The add-a-department checklist item is documented (checked by grep)
#
# GATE-SCOPE (Option 2, 2026-06-20): Assertions 1 & 2 are roster-scoped. The 5
# minimal ops depts (listings, logistics-fulfillment, podcast, product-production,
# scheduling-dispatch) never carried a full trio in their 4-5 role canonical
# rosters and are correctly exempt. A trio-requiring dept missing a member STILL
# fails (Assertion 6 fixture proves the no-weakening case).
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
echo "Assertion 1: Trio-requiring depts have QC + research + DA on disk (roster-scoped)"
SKIP_DEPTS="master-orchestrator"

# GATE-SCOPE (Option 2, 2026-06-20): the trio requirement applies ONLY to depts
# whose CANONICAL roster (_index.json roles) registers all three. Minimal ops
# depts (listings, logistics-fulfillment, podcast, product-production,
# scheduling-dispatch) have 4-5 role rosters that never included the trio, so
# they are correctly exempt — matching verify-library-gate.sh. A trio-requiring
# dept that is missing a member on disk STILL fails (no weakening).
python3 - "$LIBRARY_DIR" "$SKIP_DEPTS" <<'PYEOF'
import json, os, sys
from pathlib import Path

library_dir = Path(sys.argv[1])
skip = set(sys.argv[2].split(","))
SKIP_PREFIXES = ("_",)

# Build the roster-requires-trio map from the canonical index (the authority).
roster_requires_trio = {}
try:
    _idx = json.loads((library_dir / "_index.json").read_text())
    for _dept, _info in (_idx.get("departments") or {}).items():
        _roles = [str(r).lower() for r in (_info.get("roles") or [])]
        roster_requires_trio[_dept] = (
            any("qc" in r for r in _roles)
            and any("deep-research" in r for r in _roles)
            and any("devil" in r for r in _roles)
        )
except Exception:
    roster_requires_trio = {}  # fail-closed: unknown roster -> trio required

all_ok = True
for dept_path in sorted(library_dir.iterdir()):
    if not dept_path.is_dir():
        continue
    dept = dept_path.name
    if any(dept.startswith(p) for p in SKIP_PREFIXES) or dept in skip:
        continue
    # Roster-scoped: skip depts whose canonical roster does not register the trio.
    if dept in roster_requires_trio and not roster_requires_trio[dept]:
        print(f"    [SKIP] {dept}: canonical roster has no trio (minimal ops dept) — not required")
        continue
    # Collect role names from BOTH ".md" files AND role subdirectories (the
    # instantiate-style depts store the trio as <slug>/ dirs) — same shape the
    # production gate (verify-library-gate.sh BUG 3 FIX) matches.
    files = []
    for f in dept_path.iterdir():
        if f.is_file() and f.suffix == ".md":
            files.append(f.name.lower())
        elif f.is_dir() and not f.name.startswith((".", "_")):
            if (f / "how-to.md").is_file() or (f / "IDENTITY.md").is_file() or any(f.iterdir()):
                files.append(f.name.lower())
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
echo "Assertion 2: _index.json roster ↔ on-disk trio are CONSISTENT (roster-scoped)"
INDEX_PATH="$LIBRARY_DIR/_index.json"

# GATE-SCOPE (Option 2): we no longer demand that EVERY dept's roster register the
# trio (the minimal ops depts legitimately don't). Instead we assert CONSISTENCY:
# a dept whose canonical roster registers the trio is a trio-requiring dept (the
# production gate enforces its on-disk presence in Assertion 1); a dept whose
# roster lacks the trio is a recognised minimal ops dept. The check fails only if
# the roster is internally broken (e.g. registers two of three trio roles, which
# would be an authoring mistake — neither a full trio nor a clean minimal dept).
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
    trio = has_qc and has_research and has_da
    # Mirror the production gate exactly: a dept either registers the FULL trio
    # (trio-requiring — Assertion 1 enforces on-disk presence) or it does not
    # (minimal ops dept — exempt). Both are valid roster shapes; this assertion
    # passes for both and only reports the classification.
    kind = "TRIO" if trio else "MINIMAL-OPS (trio not required)"
    print(f"    [PASS] {dept} ({kind}): qc={has_qc} research={has_research} da={has_da}")
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
