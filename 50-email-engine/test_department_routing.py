#!/usr/bin/env python3
"""test_department_routing.py — static guard that Skill 50's Command Center board
card routes to a REAL, seeded fleet department (never a phantom slug).

THE BUG THIS KILLS
------------------
run_email_engine.py's `_mc_board_begin` hardcoded `department="email"` when
opening the run's Command Center card. "email" is NOT a seeded department
anywhere in the fleet — it is not one of the 22 mandatory canonical departments,
not one of the 6 universal-primary vertical departments, and not a variant alias
(the CRM department's one-liner merely mentions the word "email"). So every Email
Engine card silently stranded unrouted / misrouted since the skill shipped. This
is the SAME class of defect as Skill 55's old `"product-bio"` and Skill 53's
`"books"`.

Skill 50's OWN authoritative declaration
(23-ai-workforce-blueprint/skill-department-map.json) names departments
["marketing", "crm"] with the PRIMARY role (email-campaign-strategist) in
"marketing"; EMAIL-MANIFEST.json's role_reconciliation_note agrees. The board
card MUST therefore route to "marketing" — the PRIMARY owning department, matching
how the sibling Skill 55 fix (product-bio -> marketing) was resolved.

WHAT THIS TEST DOES
-------------------
An AST STATIC check — it NEVER imports or runs the orchestrator (so it needs no
front-door nonce and no live board). It parses run_email_engine.py, extracts the
`department=` literal(s) passed to mc_board's begin_run/card_open, and asserts the
literal is (a) a plain string, (b) exactly "marketing", (c) a member of the
canonical fleet department set, and (d) NEVER the broken "email". A companion
assertion proves the canonical set actually EXCLUDES "email" (so the invariant
has teeth) and INCLUDES "marketing".

Run:  python3 test_department_routing.py     (verbose unittest)
Exit: 0 = card routes to the canonical primary department; non-zero = regression.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent
_RUNNER = _SKILL_DIR / "run_email_engine.py"

# Skill 50's authoritative PRIMARY owning department (skill-department-map.json:
# skill 50 departments ["marketing","crm"], PRIMARY role email-campaign-strategist
# in "marketing"). The board card MUST route here.
EXPECTED_DEPARTMENT = "marketing"

# The exact phantom slug the bug shipped. It must NEVER reappear in the runner.
BROKEN_DEPARTMENT = "email"

# Canonical fleet department floor — 22 mandatory + 6 universal-primary vertical —
# mirrors department-floor.py's HARDCODED_MANDATORY + HARDCODED_UNIVERSAL_PRIMARY.
# Used as a fail-safe when the 23-ai-workforce-blueprint is not co-located with
# this skill (shipped standalone), so the guard still has teeth.
_FALLBACK_MANDATORY = {
    "marketing", "sales", "billing-finance", "customer-support",
    "web-development", "app-development", "graphics", "video", "audio",
    "research", "communications", "crm", "openclaw-maintenance", "legal",
    "social-media", "paid-advertisement", "personal-assistant",
    "general-task", "project-architecture-office",
    "bugs", "healer", "quality-control",
}
_FALLBACK_UNIVERSAL_PRIMARY = {
    "presentations", "scheduling-dispatch", "logistics-fulfillment",
    "engineering", "account-management", "podcast",
}


def _find_naming_map() -> Path | None:
    """Locate 23-ai-workforce-blueprint/department-naming-map.json by walking up
    from this skill dir (works in the repo layout and a co-located install)."""
    d = _SKILL_DIR
    for _ in range(8):
        cand = d / "23-ai-workforce-blueprint" / "department-naming-map.json"
        if cand.is_file():
            return cand
        if d.parent == d:
            break
        d = d.parent
    return None


def load_canonical_departments() -> set:
    """The universe of REAL fleet departments: mandatory keys + every vertical-pack
    department id. Sourced LIVE from department-naming-map.json when present; falls
    back to the mandatory + universal-primary floor otherwise."""
    mp = _find_naming_map()
    depts: set = set()
    if mp is not None:
        try:
            nm = json.loads(mp.read_text(encoding="utf-8"))
            depts |= set((nm.get("mandatory") or {}).keys())
            for pack in (nm.get("vertical_packs") or {}).values():
                if not isinstance(pack, dict):
                    continue
                for d in (pack.get("auto_add_departments") or []):
                    if isinstance(d, dict) and d.get("id"):
                        depts.add(d["id"])
        except (OSError, ValueError):
            depts = set()
    if not depts:
        depts = set(_FALLBACK_MANDATORY) | set(_FALLBACK_UNIVERSAL_PRIMARY)
    return depts


def _department_literals(func_name: str | None = None) -> list:
    """Return every string literal passed as `department=` in run_email_engine.py.
    When func_name is given, only literals inside that FunctionDef are returned.
    Non-literal (dynamic) department= values are reported as the sentinel None so a
    test can flag them (a dynamic slug can smuggle the broken value past a static
    check)."""
    tree = ast.parse(_RUNNER.read_text(encoding="utf-8"))
    scope = tree
    if func_name is not None:
        scope = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                scope = node
                break
        if scope is None:
            return []
    lits: list = []
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "department":
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        lits.append(kw.value.value)
                    else:
                        lits.append(None)  # dynamic — not a plain string literal
    return lits


class DepartmentRoutingTest(unittest.TestCase):
    def test_runner_and_begin_hook_exist(self):
        self.assertTrue(_RUNNER.is_file(), "run_email_engine.py must exist")
        src = _RUNNER.read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        self.assertIn("_mc_board_begin", names,
                      "run_email_engine.py must define _mc_board_begin (the board hook)")

    def test_begin_hook_routes_to_marketing(self):
        lits = _department_literals("_mc_board_begin")
        self.assertTrue(lits, "_mc_board_begin must pass a department= to mc_board.begin_run")
        self.assertNotIn(None, lits,
                         "department= must be a plain string LITERAL (no dynamic slug that "
                         "could smuggle a phantom department past this static check)")
        self.assertEqual(sorted(set(lits)), [EXPECTED_DEPARTMENT],
                         "the board card must route to Skill 50's PRIMARY owning "
                         "department %r (per skill-department-map.json)" % EXPECTED_DEPARTMENT)

    def test_never_the_broken_email_slug(self):
        all_lits = _department_literals()
        self.assertNotIn(
            BROKEN_DEPARTMENT, all_lits,
            "REGRESSION: department=%r is back — %r is NOT a seeded fleet department; "
            "cards would strand unrouted (route to %r instead)."
            % (BROKEN_DEPARTMENT, BROKEN_DEPARTMENT, EXPECTED_DEPARTMENT))

    def test_every_department_literal_is_canonical(self):
        canonical = load_canonical_departments()
        all_lits = [x for x in _department_literals() if x is not None]
        self.assertTrue(all_lits, "run_email_engine.py must pass at least one department=")
        for slug in all_lits:
            self.assertIn(slug, canonical,
                          "department=%r is not a real, seeded fleet department "
                          "(not in department-naming-map.json)" % slug)

    def test_canonical_set_has_teeth(self):
        """Prove the invariant is meaningful: the canonical set INCLUDES the
        expected department and EXCLUDES the broken one."""
        canonical = load_canonical_departments()
        self.assertIn(EXPECTED_DEPARTMENT, canonical,
                      "%r must be a canonical department" % EXPECTED_DEPARTMENT)
        self.assertNotIn(BROKEN_DEPARTMENT, canonical,
                         "%r must NOT be a canonical department (if it were, the whole "
                         "premise of this guard would be wrong)" % BROKEN_DEPARTMENT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
