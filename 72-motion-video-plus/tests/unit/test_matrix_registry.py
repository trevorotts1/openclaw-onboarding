"""Test matrix registry consistency tests (MG-043).

Runs the same checks as tests/check_matrix.py under the unit suite so
the registry cannot drift silently: exactly T01..T34, valid states,
evidence paths that exist for implemented/partial rows, and named
owning items for partial/pending rows.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "check_matrix", SKILL_ROOT / "tests" / "check_matrix.py"
)
check_matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_matrix)


class MatrixRegistryTests(unittest.TestCase):
    def test_registry_is_consistent(self):
        matrix = json.loads((SKILL_ROOT / "tests" / "matrix.json").read_text(encoding="utf-8"))
        problems = check_matrix.check_matrix(matrix, SKILL_ROOT)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_checker_rejects_a_row_without_evidence(self):
        matrix = json.loads((SKILL_ROOT / "tests" / "matrix.json").read_text(encoding="utf-8"))
        matrix["tests"][0]["evidence"] = []
        problems = check_matrix.check_matrix(matrix, SKILL_ROOT)
        self.assertTrue(any("no evidence" in p for p in problems), problems)

    def test_checker_rejects_a_missing_test_id(self):
        matrix = json.loads((SKILL_ROOT / "tests" / "matrix.json").read_text(encoding="utf-8"))
        matrix["tests"] = [r for r in matrix["tests"] if r["id"] != "T34"]
        problems = check_matrix.check_matrix(matrix, SKILL_ROOT)
        self.assertTrue(any("T01..T34" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
