#!/usr/bin/env python3
"""test_department_slug.py — regression test for Skill 53's Command Center department wiring.

FIX-BK-DEPT-01. Proves _mc_board_begin's `department=` argument in run_book_writer.py is a
REAL, already-seeded canonical department slug — never a fabricated one. Before this fix,
run_book_writer.py:709 hardcoded department="books", but no script anywhere in this repo ever
creates a "books" department (no workspace row, no agent runtime). mc_board.py's card_open()
fails SOFT on an unrecognized department_slug (it never raises — a board outage / bad value is
CAUGHT, LOGGED to stderr, and the run continues), so a fabricated slug never throws: every Book
Writer Command Center card was silently dropped or misrouted since the skill shipped, with no
visible error. This test is the missing guard that would have caught that regression.

Ground truth (the SAME sources tonight's fleet-wide audit used):
  - 23-ai-workforce-blueprint/department-naming-map.json  .mandatory keys (the 22 canonical
    mandatory departments department-floor.py enforces on every client build).
  - 23-ai-workforce-blueprint/skill-department-map.json   skill "53" -> departments: ["marketing"]
    (the authoritative skill-to-department binding; matches siblings 52/54/55/56, the same
    content/publishing family WIRING-SPEC.md section 8 describes).

Exit: 0 = department slug verified real + unchanged from a known-fabricated value; nonzero = FAIL.
"""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SKILL_DIR.parent
_RUN_BOOK_WRITER = _SKILL_DIR / "run_book_writer.py"
_NAMING_MAP = _REPO_ROOT / "23-ai-workforce-blueprint" / "department-naming-map.json"
_SKILL_DEPT_MAP = _REPO_ROOT / "23-ai-workforce-blueprint" / "skill-department-map.json"

# Broken-checkout safety net: mirrors department-floor.py's own HARDCODED_MANDATORY
# fallback so this test still enforces something real even if department-naming-map.json
# is unreadable (never silently pass on an empty canonical set).
_HARDCODED_MANDATORY_FALLBACK = [
    "marketing", "sales", "billing-finance", "customer-support",
    "web-development", "app-development", "graphics", "video", "audio",
    "research", "communications", "crm", "openclaw-maintenance", "legal",
    "social-media", "paid-advertisement", "personal-assistant",
    "general-task", "project-architecture-office",
    "bugs", "healer", "quality-control",
]

# The historic, confirmed-fabricated slug this regression test guards against.
_KNOWN_FABRICATED_SLUG = "books"


def canonical_mandatory_departments():
    """The live mandatory department id set, falling back to the hardcoded mirror on a
    missing/unreadable map (never silently empty)."""
    try:
        nm = json.loads(_NAMING_MAP.read_text(encoding="utf-8"))
        mand = list((nm.get("mandatory") or {}).keys())
        if mand:
            return mand
    except (OSError, ValueError):
        pass
    return list(_HARDCODED_MANDATORY_FALLBACK)


def skill_53_declared_departments():
    """The authoritative skill-department-map.json departments[] for skill "53", or None
    if the map / entry is unreadable (test degrades to the canonical-membership check only)."""
    try:
        data = json.loads(_SKILL_DEPT_MAP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for entry in data.get("skills", []):
        if isinstance(entry, dict) and str(entry.get("skill")) == "53":
            depts = entry.get("departments")
            return list(depts) if isinstance(depts, list) else None
    return None


def find_mc_board_department(source: str) -> str:
    """Statically extract the department= keyword literal passed to mc_board.begin_run(...)
    inside _mc_board_begin, via AST (never regex — a docstring or comment mentioning
    department="books" must never fool this check either way)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_mc_board_begin":
            for call_node in ast.walk(node):
                if (isinstance(call_node, ast.Call)
                        and isinstance(call_node.func, ast.Attribute)
                        and call_node.func.attr == "begin_run"):
                    for kw in call_node.keywords:
                        if kw.arg == "department" and isinstance(kw.value, ast.Constant):
                            return kw.value.value
    raise AssertionError(
        "could not find a department= keyword literal in _mc_board_begin's "
        "mc_board.begin_run(...) call in run_book_writer.py"
    )


class DepartmentSlugTest(unittest.TestCase):
    def _department(self) -> str:
        source = _RUN_BOOK_WRITER.read_text(encoding="utf-8")
        return find_mc_board_department(source)

    def test_department_is_a_real_canonical_department(self):
        dept = self._department()
        canon = canonical_mandatory_departments()
        self.assertIn(
            dept, canon,
            "run_book_writer.py's mc_board department=%r is NOT a real, seeded department "
            "(canonical mandatory set: %s). mc_board.py fails SOFT on an unrecognized "
            "department_slug -- no exception, no visible error -- so a fabricated slug "
            "silently drops/misroutes every Book Writer Command Center card." % (dept, canon)
        )

    def test_department_is_not_the_historic_fabricated_slug(self):
        dept = self._department()
        self.assertNotEqual(
            dept, _KNOWN_FABRICATED_SLUG,
            "REGRESSION: run_book_writer.py reverted to the fabricated %r department slug. "
            "No script anywhere in this repo creates that department; see WIRING-SPEC.md "
            "section 8 for the correct owning department (the Content/Publishing lineage, "
            "resolved by skill-department-map.json to 'marketing')." % _KNOWN_FABRICATED_SLUG
        )

    def test_department_matches_authoritative_skill_map(self):
        dept = self._department()
        declared = skill_53_declared_departments()
        if declared is None:
            self.skipTest("skill-department-map.json unreadable or has no skill=53 entry")
        self.assertIn(
            dept, declared,
            "run_book_writer.py's mc_board department=%r does not match "
            "skill-department-map.json's skill-53 departments=%s (the authoritative "
            "skill-to-department binding)." % (dept, declared)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
