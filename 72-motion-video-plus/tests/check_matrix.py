"""Validate the MG-043 test matrix registry (tests/matrix.json).

The registry is the change ledger's map from directive test IDs (T01-T34)
to the evidence that implements them today or the item that owns them
tomorrow. This checker keeps that map honest:

- exactly the IDs T01..T34, each once;
- every row has a name, at least one subject item in MG-001..MG-050, a
  state (implemented / partial / pending), and a good/bad gate pair;
- implemented and partial rows cite evidence paths that exist on disk
  (relative to the skill root); a row may not claim implementation with
  no evidence;
- partial and pending rows name their owning item(s) in blocked_on, and
  blocked_on entries are valid MG IDs disjoint from the row's evidence
  claim (a row cannot be both fully evidenced and blocked without saying
  which part is which, which is what its notes are for).

Exit 0 when the registry is consistent, 1 otherwise. Run directly or via
tests/unit/test_matrix_registry.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = SKILL_ROOT / "tests" / "matrix.json"

EXPECTED_IDS = [f"T{n:02d}" for n in range(1, 35)]
VALID_STATES = ("implemented", "partial", "pending")
MG_IDS = {f"MG-{n:03d}" for n in range(1, 51)}


def check_matrix(matrix: dict, skill_root: Path) -> list[str]:
    problems: list[str] = []
    rows = matrix.get("tests")
    if not isinstance(rows, list):
        return ["matrix.tests is not a list"]
    ids = [r.get("id") for r in rows]
    if sorted(ids) != EXPECTED_IDS:
        problems.append(
            f"test IDs must be exactly T01..T34 once each; got {sorted(ids)}"
        )
    for row in rows:
        rid = row.get("id", "<missing id>")
        if row.get("state") not in VALID_STATES:
            problems.append(f"{rid}: state {row.get('state')!r} not in {VALID_STATES}")
        if not row.get("name"):
            problems.append(f"{rid}: missing name")
        subjects = row.get("subject_items") or []
        if not subjects or any(s not in MG_IDS for s in subjects):
            problems.append(f"{rid}: subject_items must be non-empty MG-001..MG-050, got {subjects}")
        gate = row.get("gate") or {}
        if not gate.get("good") or not gate.get("bad"):
            problems.append(f"{rid}: gate must describe a known-good and a known-bad case")
        evidence = row.get("evidence") or []
        blocked = row.get("blocked_on") or []
        if any(b not in MG_IDS for b in blocked):
            problems.append(f"{rid}: blocked_on must name MG IDs, got {blocked}")
        state = row.get("state")
        if state in ("implemented", "partial"):
            if not evidence:
                problems.append(f"{rid}: state {state} but no evidence cited")
            for rel in evidence:
                if not (skill_root / rel).exists():
                    problems.append(f"{rid}: evidence path does not exist: {rel}")
        if state == "implemented" and blocked:
            problems.append(f"{rid}: implemented rows must not carry blocked_on (use partial)")
        if state in ("partial", "pending") and not blocked:
            problems.append(f"{rid}: state {state} but blocked_on names no owning item")
        if state == "pending" and evidence:
            problems.append(f"{rid}: pending rows must not cite evidence as if implemented")
    return problems


def main() -> int:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    problems = check_matrix(matrix, SKILL_ROOT)
    counts: dict[str, int] = {}
    for row in matrix["tests"]:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    print(
        "matrix: {total} rows ({detail})".format(
            total=len(matrix["tests"]),
            detail=", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
        )
    )
    if problems:
        for p in problems:
            print(f"FAIL {p}")
        return 1
    print("matrix registry consistent: every implemented/partial row's evidence exists; every partial/pending row names its owner.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
