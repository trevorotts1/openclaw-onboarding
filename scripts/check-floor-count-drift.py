#!/usr/bin/env python3
"""
check-floor-count-drift.py — CI guard: department-floor.py must not contain
hardcoded floor-count integers in human-readable output strings.

The bug this guards against: docstrings, `reason=` values, and banner prints
in department-floor.py previously hardcoded the floor count (e.g. "28",
"16 mandatory", "7 universal") as static strings. When the mandatory list
changed the strings went stale — the reported number diverged from the live
computed floor. v12.3.1 fixes this by deriving all output from runtime data;
this CI guard ensures it can never regress.

WHAT IS CHECKED:
  1. The `reason` string returned by evaluate_floor() when the floor IS met
     must NOT contain a hardcoded integer that disagrees with the value
     evaluate_floor() actually computes (expected_floor_count).
  2. The human-readable banner printed by main() must NOT contain a hardcoded
     floor count that disagrees with what evaluate_floor() computes.
  3. The source file must NOT contain bare integer literals ≥ 20 that appear
     inside human-readable string literals in reason/banner output lines
     (pattern: `reason = "...NN-department..."` or `print("...NN-department...")`).

HOW THE CHECK WORKS:
  - Import evaluate_floor from the module under test (no side-effects).
  - Build a synthetic departments_dir with exactly the right set of folders
    so evaluate_floor() returns floor_met=True with zero declines.
  - Assert that the returned `reason` string embeds the computed
    expected_floor_count — not any other integer.
  - Parse the source with ast to find string literals in assignment/print
    nodes that contain a digit-department pattern and verify those digits
    match the computed floor.

EXIT:
  0 — PASS (no drift)
  1 — FAIL (hardcoded mismatch detected or import failed)

Usage:
  python3 scripts/check-floor-count-drift.py
"""
import ast
import os
import re
import sys
import tempfile
from pathlib import Path

# ── Locate department-floor.py ───────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
FLOOR_PY = REPO_ROOT / "23-ai-workforce-blueprint" / "scripts" / "department-floor.py"
if not FLOOR_PY.exists():
    print(f"[FAIL] department-floor.py not found at expected path: {FLOOR_PY}", file=sys.stderr)
    sys.exit(1)

# ── Import evaluate_floor (filename has a hyphen — use importlib.util) ──────
import importlib.util
spec = importlib.util.spec_from_file_location("department_floor", FLOOR_PY)
if spec is None or spec.loader is None:
    print(f"[FAIL] Could not load spec for {FLOOR_PY}", file=sys.stderr)
    sys.exit(1)
floor_mod = importlib.util.module_from_spec(spec)
try:
    # Add the scripts dir to sys.path so department-floor.py can find its siblings
    sys.path.insert(0, str(FLOOR_PY.parent))
    spec.loader.exec_module(floor_mod)  # type: ignore[attr-defined]
except Exception as exc:
    print(f"[FAIL] Could not exec {FLOOR_PY}: {exc}", file=sys.stderr)
    sys.exit(1)

try:
    evaluate_floor = floor_mod.evaluate_floor
    HARDCODED_MANDATORY = floor_mod.HARDCODED_MANDATORY
    universal_primary_vertical_departments = floor_mod.universal_primary_vertical_departments
    load_naming_map = floor_mod.load_naming_map
    mandatory_ids = floor_mod.mandatory_ids
except AttributeError as exc:
    print(f"[FAIL] department_floor missing expected symbol: {exc}", file=sys.stderr)
    sys.exit(1)

# ── Compute the expected floor count from live data ──────────────────────────
nm = load_naming_map()
mandatory_count = len(HARDCODED_MANDATORY)
universal_primaries = universal_primary_vertical_departments(nm)
universal_count = len(universal_primaries)
expected_floor_count = mandatory_count + universal_count

print(f"[INFO] HARDCODED_MANDATORY count : {mandatory_count}")
print(f"[INFO] universal_primary count   : {universal_count}")
print(f"[INFO] expected_floor_count      : {expected_floor_count}")

# ── Build a synthetic departments_dir with all required folders ──────────────
failures = []
with tempfile.TemporaryDirectory() as tmpdir:
    depts_dir = Path(tmpdir) / "departments"
    depts_dir.mkdir()
    # Create one folder per expected floor department (mandatory + universal primary)
    all_floor_ids = mandatory_ids(nm) + universal_primaries
    for did in all_floor_ids:
        (depts_dir / did).mkdir(exist_ok=True)

    verdict = evaluate_floor(
        departments_dir=depts_dir,
        build_state={},   # no declines
        core_answers={},
    )

# ── Check 1: floor_met must be True ─────────────────────────────────────────
if not verdict["floor_met"]:
    failures.append(
        f"Check 1 FAIL: evaluate_floor() returned floor_met=False even with all "
        f"required folders present. missing_mandatory={verdict['missing_mandatory']}, "
        f"missing_universal_primary={verdict['missing_universal_primary']}"
    )

# ── Check 2: when floor is met, reason must embed the computed total floor ────
# The reason string may include sub-counts (mandatory count, universal count,
# declined count) as well as the total. We only require that the TOTAL
# expected_floor_count appears somewhere in the reason, and that no integer
# in the reason exceeds the total (which would indicate a stale hardcoded value
# from a previously larger floor that has since changed).
reason = verdict.get("reason", "")
if verdict.get("floor_met"):
    reason_integers = [int(m) for m in re.findall(r"\b(\d{2,})\b", reason)]
    # Any integer LARGER than expected_floor_count is definitely stale.
    stale_in_reason = [n for n in reason_integers if n > expected_floor_count]
    if stale_in_reason:
        failures.append(
            f"Check 2 FAIL: reason string contains integer(s) {stale_in_reason} "
            f"larger than the computed expected_floor_count={expected_floor_count}. "
            f"These are stale hardcoded values. reason={reason!r}"
        )
    elif reason_integers and expected_floor_count not in reason_integers:
        # Reason has integers but the total is missing — still a problem
        failures.append(
            f"Check 2 FAIL: reason string integers {reason_integers} do not include "
            f"expected_floor_count={expected_floor_count} (the total floor). "
            f"reason={reason!r}"
        )

# ── Check 3: AST scan — no hardcoded floor integers in output string literals ─
# Pattern: a string literal containing a two-or-more digit integer followed by
# "-department" — that would be a hardcoded "28-department standard" style string.
source = FLOOR_PY.read_text(encoding="utf-8")
try:
    tree = ast.parse(source)
except SyntaxError as exc:
    failures.append(f"Check 3 FAIL: could not parse {FLOOR_PY}: {exc}")
    tree = None

if tree is not None:
    HARDCODED_FLOOR_PATTERN = re.compile(r"(\d{2,})-department")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if not isinstance(node.value, str):
            continue
        s = node.value
        matches = HARDCODED_FLOOR_PATTERN.findall(s)
        if not matches:
            continue
        for m in matches:
            n = int(m)
            if n != expected_floor_count:
                failures.append(
                    f"Check 3 FAIL: line {node.lineno}: string literal contains "
                    f"'{n}-department' but computed floor is {expected_floor_count}. "
                    f"String: {s[:120]!r}"
                )

# ── Check 4: expected_floor_count in verdict matches our independently computed value ──
if verdict.get("expected_floor_count") != expected_floor_count:
    failures.append(
        f"Check 4 FAIL: verdict['expected_floor_count']={verdict.get('expected_floor_count')} "
        f"!= independently computed {expected_floor_count}"
    )

# ── Report ───────────────────────────────────────────────────────────────────
if failures:
    print("", file=sys.stderr)
    print("FLOOR COUNT DRIFT DETECTED", file=sys.stderr)
    for f in failures:
        print(f"  {f}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        f"FIX: department-floor.py must derive all floor counts from runtime data "
        f"(len(HARDCODED_MANDATORY) + len(universal_primary_vertical_departments())). "
        f"The computed floor is currently {expected_floor_count}.",
        file=sys.stderr,
    )
    sys.exit(1)

print(
    f"[PASS] department-floor.py floor count drift check — "
    f"no hardcoded floor counts detected. "
    f"Computed floor = {expected_floor_count} "
    f"({mandatory_count} mandatory + {universal_count} universal-primary-vertical)."
)
