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

# ── Check 3: scan for hardcoded floor integers — string literals AND comments ─
# TWO FIXES over the original Check 3 (both proven blind by the OQ-7-style drift
# this file itself carried until v2.8.0: stale "22 + 6 = 28" / "23 + 6 = 29"
# comments sat right next to a module docstring that had already moved past
# them, and Check 3 never caught it):
#
#   1. PATTERN was ONLY `(\d{2,})-department` (a literal hyphen joining the
#      number to the word "department"). None of this file's actual floor
#      prose is phrased that way — it is phrased as "NN mandatory", "NN
#      universal-primary", and "A + B = NN" arithmetic. HARDCODED_FLOOR_PATTERNS
#      below adds all three so an equation like "22 + 6 = 28" or a bare
#      "23 mandatory canonical" is no longer invisible to this guard.
#   2. SOURCE was ONLY ast.Constant string literals (docstrings, print() /
#      f-string arguments) via ast.walk(). Python's ast module does not
#      represent `#` comments at all — they are discarded by the tokenizer
#      before parsing ever sees them — so every one of this file's extensive
#      `#`-prefixed explanatory comments (which is where MOST of its floor
#      prose actually lives) was structurally invisible to Check 3, no matter
#      what pattern it used. COMMENT_TEXTS below extracts real COMMENT tokens
#      via the `tokenize` module (the correct way to see comments — never
#      regex-split on a bare "#", which false-fires inside string literals)
#      and scans them with the same pattern set.
source = FLOOR_PY.read_text(encoding="utf-8")

# Each pattern is paired with the QUANTITY it captures — "NN mandatory" and
# "NN universal-primary" are legitimate SUB-counts (must equal mandatory_count
# / universal_count respectively, NOT the total floor), while "NN-department"
# and "A + B = NN" arithmetic assert the TOTAL. Comparing every capture against
# expected_floor_count (the original design's implicit assumption) would make
# a CORRECT "24 mandatory" line false-fire, since 24 != 30.
HARDCODED_FLOOR_PATTERNS = [
    # "28-department" / "30-department" (original pattern, kept) — TOTAL.
    (re.compile(r"(\d{2,})-department"), "expected_floor_count"),
    # "22 mandatory" / "23 mandatory canonical" (word boundary so "223" or an
    # ordinal like "23rd mandatory" does not false-match) — MANDATORY sub-count.
    (re.compile(r"\b(\d{2,})\s+mandatory\b"), "mandatory_count"),
    # "7 universal-primary" / "6 universal primary" — UNIVERSAL-PRIMARY sub-count.
    (re.compile(r"\b(\d+)\s+universal[\s-]primary\b"), "universal_count"),
    # "22 + 6 = 28" style arithmetic — capture the right-hand TOTAL.
    (re.compile(r"\d+\s*\+\s*\d+\s*=\s*(\d{2,})\b"), "expected_floor_count"),
]
_EXPECTED_VALUES = {
    "expected_floor_count": expected_floor_count,
    "mandatory_count": mandatory_count,
    "universal_count": universal_count,
}


def _find_floor_mismatches(text, line_no, label):
    out = []
    for pattern, quantity in HARDCODED_FLOOR_PATTERNS:
        expected = _EXPECTED_VALUES[quantity]
        for m in pattern.finditer(text):
            n = int(m.group(1))
            if n != expected:
                out.append(
                    f"Check 3 FAIL: {label} line {line_no}: contains "
                    f"'{m.group(0)}' ({quantity}={n}) but computed {quantity}={expected}. "
                    f"Text: {text[max(0, m.start() - 40):m.end() + 20]!r}"
                )
    return out


try:
    tree = ast.parse(source)
except SyntaxError as exc:
    failures.append(f"Check 3 FAIL: could not parse {FLOOR_PY}: {exc}")
    tree = None

if tree is not None:
    # 3a. String literals (docstrings, print()/f-string arguments).
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if not isinstance(node.value, str):
            continue
        failures.extend(_find_floor_mismatches(node.value, node.lineno, "string literal"))

    # 3b. `#` comments — invisible to ast.walk(); tokenize is the only correct
    # way to see them (a bare `"#" in line` regex would false-fire on a "#"
    # that appears inside a string literal, e.g. a URL fragment or MCP-server
    # id, of which this file's later utility code has a few).
    try:
        import io
        import tokenize as _tokenize
        for tok in _tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == _tokenize.COMMENT:
                failures.extend(_find_floor_mismatches(tok.string, tok.start[0], "comment"))
    except _tokenize.TokenizeError as exc:  # pragma: no cover - defensive
        failures.append(f"Check 3 FAIL: could not tokenize {FLOOR_PY} for comments: {exc}")

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
