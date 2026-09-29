#!/usr/bin/env python3
"""The interview build's role folders meet the role-library floor the prover enforces.

  * Every role folder carries the library's canonical slug. The suggested-roles
    headers carry employment tags ("Director of CRM (full-time-permanent)"), and
    the build used to name the folder "01-director-of-crm-full-time-permanent".
  * Every library role of the department is built (healer, devil's advocate,
    SOP writer, ...), not only the roles the roster lists.
  * Idempotent: a second build adds nothing.

Matching uses the floor prover's own rule: strip the NN- prefix, fold '--' to '-'.
Run: python3 tests/unit/test_build_library_role_floor.py
"""
import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "23-ai-workforce-blueprint"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BW = _load("bw_role_floor_test", SKILL / "scripts" / "build-workforce.py")
INDEX = json.loads((SKILL / "templates" / "role-library" / "_index.json").read_text())


def prover_key(name):
    return re.sub(r"-{2,}", "-", re.sub(r"^\d+[-_]", "", name).lower())


class TestBuildMeetsLibraryFloor(unittest.TestCase):
    DEPTS = ("crm", "sales", "marketing")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.ws = base / "workspace"
        self.depts = self.ws / "company" / "departments"
        self.depts.mkdir(parents=True)
        (base / ".openclaw").mkdir()
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = str(base)
        for f in ("AGENTS.md", "TOOLS.md", "USER.md"):
            (self.ws / f).write_text(f"canonical {f}\n" * 50)
        self._saved = {k: getattr(BW, k) for k in ("WORKSPACE_ROOT", "DEPARTMENTS_DIR", "COMPANY_SLUG")}
        BW.WORKSPACE_ROOT = str(self.ws)
        BW.DEPARTMENTS_DIR = str(self.depts)
        BW.COMPANY_SLUG = "fixture-co"

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(BW, k, v)
        os.environ["HOME"] = self._home
        self._tmp.cleanup()

    def build(self, dept):
        info = {"name": dept.title(), "emoji": "*", "head": f"{dept} head", "description": f"{dept} work"}
        answers = {"company_name": "Fixture Co"}
        BW.create_department_workspace(dept, info, answers)
        BW.create_role_workspace(dept, info, answers)
        return sorted(p.name for p in (self.depts / dept).iterdir()
                      if p.is_dir() and re.match(r"^\d+-", p.name))

    def test_folders_use_library_slugs_and_cover_the_library(self):
        for dept in self.DEPTS:
            with self.subTest(dept=dept):
                folders = self.build(dept)
                self.assertFalse([f for f in folders if re.search(r"full-time|permanent|on-call", f)], folders)
                keys = [prover_key(f) for f in folders]
                self.assertEqual(len(keys), len(set(keys)), f"two folders for one role: {folders}")
                on_disk = {prover_key(p.name) for p in (self.depts / dept).iterdir() if p.is_dir()}
                missing = {prover_key(s) for s in INDEX["departments"][dept]["roles"]} - on_disk
                self.assertEqual(missing, set(), f"{dept}: library roles not built")

    def test_second_build_adds_nothing(self):
        first = self.build("crm")
        self.assertEqual(self.build("crm"), first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
