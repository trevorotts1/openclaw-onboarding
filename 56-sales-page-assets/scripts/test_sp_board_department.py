#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sp_board_department.py — regression lock for the Command Center board
department slug (Skill 56, Sales Page Assets).

THE BUG THIS KILLS
  `run_sales_page_assets.py::_mc_board_begin` posts this run's ONE Kanban card to
  the Command Center via the shared `mc_board.begin_run(..., department=<slug>)`
  helper. `mc_board` is generic and does NOT validate the department — it forwards
  whatever slug it is handed straight to the board. If that slug is not a REAL,
  seeded department, the card silently misroutes / is dropped and the run is
  invisible on the board. The skill shipped with `department="funnels"`, which is
  NOT one of the fleet's canonical departments (identical in shape to Skill 53's
  `department="books"` defect). Every Sales Page Assets card was silently dropped.

WHAT THIS TEST PROVES (static, AST-based — never runs the orchestrator)
  1. `_mc_board_begin` DOES call the board helper with a `department=` keyword whose
     value is a plain string LITERAL (not computed / not absent) — fail-closed:
     an inability to statically resolve the literal is a FAILURE, so the guard can
     never silently pass.
  2. That literal is a member of the canonical department set
     (23-ai-workforce-blueprint/department-naming-map.json: 22 mandatory + the
     universal-primary vertical-pack departments — mirrored here so the check is
     self-contained on a standalone install, and ALSO cross-checked against the
     live map when it is resolvable in the repo).
  3. That literal is NEVER one of the known-broken slugs ("funnels", "books").
  4. It matches Skill 56's OWN authoritative declared PRIMARY department
     ("marketing") per 23-ai-workforce-blueprint/skill-department-map.json.

Stdlib only (ast / json / unittest). Read-only. Zero network.

Run:  python3 test_sp_board_department.py         (verbose unittest)
Exit: 0 = the board department slug is canonical + correct; non-zero otherwise.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent            # 56-sales-page-assets/scripts
SKILL_DIR = HERE.parent                            # 56-sales-page-assets
ORCH = SKILL_DIR / "run_sales_page_assets.py"

# The board-routing helper entry points a producer may open its card through.
_BOARD_OPENERS = ("begin_run", "card_open")

# Known-broken department slugs that have shipped and silently misrouted cards.
# "funnels" = Skill 56's own historical defect; "books" = Skill 53's sibling defect.
BROKEN_SLUGS = frozenset({"funnels", "books"})

# Skill 56's authoritative PRIMARY owning department. Source of truth:
# 23-ai-workforce-blueprint/skill-department-map.json -> skill "56" ->
# roles[].primary == true is under dept "marketing" (web-development is secondary).
EXPECTED_PRIMARY_DEPARTMENT = "marketing"

# The canonical department floor, mirrored from
# 23-ai-workforce-blueprint/scripts/department-floor.py (HARDCODED_MANDATORY +
# HARDCODED_UNIVERSAL_PRIMARY). Embedded so this guard enforces even when the
# skill is installed WITHOUT the blueprint dir adjacent; the live map is ALSO
# consulted (below) when it is resolvable, so the two can never silently diverge.
CANONICAL_MANDATORY = frozenset({
    "marketing", "sales", "billing-finance", "customer-support",
    "web-development", "app-development", "graphics", "video", "audio",
    "research", "communications", "crm", "openclaw-maintenance", "legal",
    "social-media", "paid-advertisement", "personal-assistant",
    "general-task", "project-architecture-office",
    "bugs", "healer", "quality-control",
})
CANONICAL_UNIVERSAL_PRIMARY = frozenset({
    "presentations", "scheduling-dispatch", "logistics-fulfillment",
    "engineering", "account-management", "podcast",
})
CANONICAL_DEPARTMENTS = CANONICAL_MANDATORY | CANONICAL_UNIVERSAL_PRIMARY


def _extract_board_departments(source: str):
    """Statically pull every `department=<literal>` handed to a board opener
    (begin_run / card_open) in the orchestrator source. Returns a list of the
    string literals found. A non-literal (computed) department yields the sentinel
    None so the caller can fail closed."""
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else "")
        if name not in _BOARD_OPENERS:
            continue
        for kw in node.keywords:
            if kw.arg == "department":
                val = kw.value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    found.append(val.value)
                else:
                    found.append(None)   # computed / non-literal -> fail closed
    return found


def _live_canonical_departments():
    """Best-effort: load the LIVE canonical department set from the blueprint's
    department-naming-map.json when it is resolvable in the repo. Returns a set,
    or None when the map is not adjacent (standalone install)."""
    nm_path = SKILL_DIR.parent / "23-ai-workforce-blueprint" / "department-naming-map.json"
    if not nm_path.is_file():
        return None
    try:
        nm = json.loads(nm_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    depts = set((nm.get("mandatory") or {}).keys())
    for pack in (nm.get("vertical_packs") or {}).values():
        for dept in (pack.get("auto_add_departments") or []):
            did = dept.get("id") if isinstance(dept, dict) else None
            if did:
                depts.add(did)
    return depts or None


class BoardDepartmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assertTrueMsg = None
        cls.source = ORCH.read_text(encoding="utf-8")
        cls.departments = _extract_board_departments(cls.source)

    # ---- the literal is present + statically resolvable (fail-closed) ----------
    def test_board_department_literal_present(self):
        self.assertTrue(ORCH.is_file(), f"orchestrator not found at {ORCH}")
        self.assertTrue(self.departments,
                        "no board opener (begin_run/card_open) with a department= "
                        "keyword was found — the card-routing seam is missing or renamed")
        self.assertNotIn(None, self.departments,
                         "a board department= is a COMPUTED expression, not a string "
                         "literal — it cannot be statically audited (fail-closed)")

    # ---- never a known-broken slug --------------------------------------------
    def test_board_department_never_broken(self):
        for dept in self.departments:
            self.assertNotIn(
                dept, BROKEN_SLUGS,
                f"board department {dept!r} is a KNOWN-BROKEN slug (never a seeded "
                f"department) — cards route to a phantom column and are dropped")

    # ---- is a real, canonical department --------------------------------------
    def test_board_department_is_canonical(self):
        for dept in self.departments:
            self.assertIn(
                dept, CANONICAL_DEPARTMENTS,
                f"board department {dept!r} is not a canonical fleet department "
                f"(22 mandatory + 6 universal-primary, per department-naming-map.json)")

    def test_board_department_matches_live_map_when_available(self):
        live = _live_canonical_departments()
        if live is None:
            self.skipTest("department-naming-map.json not adjacent (standalone install)")
        for dept in self.departments:
            self.assertIn(
                dept, live,
                f"board department {dept!r} is absent from the LIVE "
                f"department-naming-map.json canonical set")

    # ---- matches Skill 56's declared PRIMARY owning department -----------------
    def test_board_department_is_declared_primary(self):
        for dept in self.departments:
            self.assertEqual(
                dept, EXPECTED_PRIMARY_DEPARTMENT,
                f"board department {dept!r} != Skill 56's declared PRIMARY department "
                f"{EXPECTED_PRIMARY_DEPARTMENT!r} (skill-department-map.json skill 56)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
