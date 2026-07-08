#!/usr/bin/env python3
"""test_sf_department.py — AST regression guard for the Command Center board
department slug (FIX-BOARD-DEPT-01).

WHY THIS EXISTS (the bug it kills):
  The board card each run posts (run_signature_funnel._mc_board_begin ->
  mc_board.begin_run -> card_open, which sends `department_slug=<department>` to
  POST /api/tasks/ingest) is routed to a Command Center department by that slug.
  Skill 49 shipped hardcoding department="funnels" — but "funnels" is NOT a real,
  seeded fleet department: it is absent from the 22 mandatory departments and the
  universal-primary vertical departments in
  23-ai-workforce-blueprint/department-naming-map.json and from the canonical set
  enforced by 23-ai-workforce-blueprint/scripts/department-floor.py. A card posted
  to a non-existent department slug is silently dropped / misrouted, so every
  Signature Funnel run was invisible on the kanban. (Identical in shape to the
  Skill 53 Book Writer department="books" defect.)

WHAT THIS PROVES (static — no import, no network):
  It parses run_signature_funnel.py with `ast` and, for EVERY `department=<...>`
  keyword literal passed to a board call, asserts the slug:
    1. is a STRING literal (never a computed / None value),
    2. is one of Skill 49's OWN authoritatively-declared departments in
       23-ai-workforce-blueprint/skill-department-map.json
       (web-development / marketing),
    3. is a real seeded fleet department (present in department-naming-map.json's
       mandatory set or a vertical pack), and
    4. is NEVER the historically-broken slug "funnels" (nor the sibling Skill 53
       "books" defect).
  At least one such board literal MUST exist (proving the seam is wired at all).

Run:   python3 test_sf_department.py       (verbose)
Exit:  0 = department slug canonical; nonzero = drift / the bug regressed.
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _SKILL_DIR.parent
_ORCH = _SKILL_DIR / "run_signature_funnel.py"
_BLUEPRINT = _REPO_ROOT / "23-ai-workforce-blueprint"
_SKILL_DEPT_MAP = _BLUEPRINT / "skill-department-map.json"
_NAMING_MAP = _BLUEPRINT / "department-naming-map.json"

# The slug(s) a board call is allowed to use MUST NEVER include these. "funnels"
# is the exact defect this test locks out; "books" is the sibling Skill 53 defect,
# guarded here so a copy/paste can never reintroduce EITHER broken value.
FORBIDDEN_SLUGS = frozenset({"funnels", "books"})

# Fail-safe fallbacks used ONLY when the blueprint maps are not present alongside
# the skill (e.g. a standalone install). On the full repo the live maps are read.
_FALLBACK_ALLOWED = frozenset({"web-development", "marketing"})
_FALLBACK_CANONICAL = frozenset({
    # 22 mandatory (department-floor.HARDCODED_MANDATORY)
    "marketing", "sales", "billing-finance", "customer-support",
    "web-development", "app-development", "graphics", "video", "audio",
    "research", "communications", "crm", "openclaw-maintenance", "legal",
    "social-media", "paid-advertisement", "personal-assistant",
    "general-task", "project-architecture-office", "bugs", "healer",
    "quality-control",
    # 6 universal-primary vertical departments
    "presentations", "scheduling-dispatch", "logistics-fulfillment",
    "engineering", "account-management", "podcast",
})


def _load_skill49_declared_departments() -> frozenset:
    """Skill 49's authoritatively-declared department slugs, read from the ONE
    source of truth (skill-department-map.json). Falls back to the known pair when
    the map is not shipped alongside the skill."""
    try:
        data = json.loads(_SKILL_DEPT_MAP.read_text(encoding="utf-8"))
        for entry in data.get("skills", []):
            if str(entry.get("skill")).lstrip("0") == "49":
                depts = entry.get("departments") or []
                if depts:
                    return frozenset(str(d).strip() for d in depts if str(d).strip())
    except (OSError, ValueError, TypeError):
        pass
    return _FALLBACK_ALLOWED


def _load_canonical_department_universe() -> frozenset:
    """Every real, seeded fleet department id: the mandatory set plus every
    vertical-pack department id, read from department-naming-map.json. Falls back
    to the hardcoded mandatory + universal-primary set on a standalone install."""
    try:
        nm = json.loads(_NAMING_MAP.read_text(encoding="utf-8"))
        ids = set((nm.get("mandatory") or {}).keys())
        for pack in (nm.get("vertical_packs") or {}).values():
            for dept in (pack.get("auto_add_departments") or []):
                did = dept.get("id") if isinstance(dept, dict) else None
                if did:
                    ids.add(str(did).strip())
        if ids:
            return frozenset(ids)
    except (OSError, ValueError, TypeError):
        pass
    return _FALLBACK_CANONICAL


def _board_department_literals(source: str):
    """Every `department=<const-or-not>` keyword passed to a board Call in the
    source. Returns a list of (lineno, node) where node is the keyword's value AST
    node (so a non-literal is still surfaced and can be failed)."""
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "department":
                found.append((getattr(kw.value, "lineno", node.lineno), kw.value))
    return found


class DepartmentSlugTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = _ORCH.read_text(encoding="utf-8")
        cls.literals = _board_department_literals(cls.source)
        cls.allowed = _load_skill49_declared_departments()
        cls.canonical = _load_canonical_department_universe()

    def test_a_board_seam_is_wired(self):
        self.assertTrue(
            self.literals,
            "no department= keyword found in run_signature_funnel.py — the "
            "Command Center board seam is missing (mc_board.begin_run is unwired).")

    def test_b_declared_set_is_real(self):
        # Sanity: Skill 49's declared departments must themselves be real fleet
        # departments — otherwise the ground truth we validate against is wrong.
        self.assertTrue(self.allowed)
        for slug in self.allowed:
            self.assertIn(
                slug, self.canonical,
                f"Skill 49 declares department {slug!r} but it is not a seeded "
                f"fleet department in department-naming-map.json")

    def test_c_every_board_slug_is_a_string_literal(self):
        for lineno, node in self.literals:
            self.assertIsInstance(
                node, ast.Constant,
                f"department= at line {lineno} is not a string literal "
                f"(got {type(node).__name__}); cannot statically prove routing.")
            self.assertIsInstance(
                node.value, str,
                f"department= at line {lineno} is a non-string constant "
                f"{node.value!r}.")

    def test_d_no_broken_slug(self):
        for lineno, node in self.literals:
            val = getattr(node, "value", None)
            self.assertNotIn(
                val, FORBIDDEN_SLUGS,
                f"REGRESSION: department={val!r} at line {lineno} is a NON-EXISTENT "
                f"fleet department — the board card will be silently dropped/misrouted "
                f"(this is exactly the FIX-BOARD-DEPT-01 / Skill 53 'books' bug).")

    def test_e_slug_is_declared_and_canonical(self):
        for lineno, node in self.literals:
            val = getattr(node, "value", None)
            self.assertIn(
                val, self.allowed,
                f"department={val!r} at line {lineno} is not one of Skill 49's "
                f"authoritatively-declared departments {sorted(self.allowed)} "
                f"(skill-department-map.json).")
            self.assertIn(
                val, self.canonical,
                f"department={val!r} at line {lineno} is not a real seeded fleet "
                f"department (department-naming-map.json).")


if __name__ == "__main__":
    unittest.main(verbosity=2)
