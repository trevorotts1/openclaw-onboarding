#!/usr/bin/env python3
"""reconcile-role-floor.py on a tree an older interview build left below the floor.

Field shape: crm has the nine roster roles under suffixed names
("01-director-of-crm-full-time-permanent", ...), each with a substantive how-to,
and none of the library-only roles (healer, devil's advocate, SOP writer).
After --apply:
  * every suffixed folder carries its canonical library slug and its how-to is
    byte-identical;
  * every library role of the department is present;
  * a folder whose canonical twin already exists is left alone and reported;
  * --add-floor-departments adds standard-floor departments only, never a
    library department outside the floor (another client's custom lanes);
  * a second --apply changes nothing; a dry run changes nothing.

Run: python3 tests/unit/test_reconcile_role_floor.py
"""
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "23-ai-workforce-blueprint" / "scripts"
INDEX = json.loads((ROOT / "23-ai-workforce-blueprint/templates/role-library/_index.json").read_text())
SUFFIXED = ["01-director-of-crm-full-time-permanent", "02-crm-platform-administrator-full-time-permanent",
            "03-email-deliverability-optimization-specialist-flagship-role-full-time-permanent",
            "04-sms-whatsapp-dm-sequence-specialist-full-time-permanent",
            "05-tag-segmentation-specialist-full-time-permanent",
            "06-automation-workflow-specialist-full-time-permanent",
            "07-pipeline-stage-specialist-full-time-permanent", "08-qc-role-crm-full-time-permanent",
            "09-deep-research-role-crm-on-call"]
OTHER_CLIENT = ["client-experience-booking", "founding-member-concierge", "launch-operations", "product-production"]
FILES = ("IDENTITY.md", "SOUL.md", "MEMORY.md", "HEARTBEAT.md", "how-to.md")


def _load():
    spec = importlib.util.spec_from_file_location("reconcile_role_floor", SCRIPTS / "reconcile-role-floor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def key(name):
    return re.sub(r"-{2,}", "-", re.sub(r"^\d+[-_]", "", name).lower())


def snapshot(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir")
            for p in sorted(root.rglob("*"))}


class TestReconcileRoleFloor(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self._t.name))
        self._home = os.environ["HOME"]
        os.environ["HOME"] = str(base)
        (base / ".openclaw").mkdir()
        self.company = base / "zero-human-company" / "acme"
        self.depts = self.company / "departments"
        crm = self.depts / "crm"
        for name in SUFFIXED:
            for f in FILES:
                (crm / name).mkdir(parents=True, exist_ok=True)
                (crm / name / f).write_text(f"SUBSTANTIVE {name} {f}\n" * 40)
        # sales: a suffixed folder whose canonical twin already exists -> conflict, both kept
        for name in ("03-closer-full-time-permanent", "03-closer"):
            for f in FILES:
                (self.depts / "sales" / name).mkdir(parents=True, exist_ok=True)
                (self.depts / "sales" / name / f).write_text(f"{name} {f}\n" * 40)
        self.rrf = _load()

    def tearDown(self):
        os.environ["HOME"] = self._home
        self._t.cleanup()

    def run_it(self, *args):
        out = StringIO()
        with redirect_stdout(out):
            rc = self.rrf.main(["--departments", str(self.depts), *args])
        return rc, out.getvalue()

    def test_dry_run_changes_nothing(self):
        before = snapshot(self.depts)
        rc, out = self.run_it()
        self.assertEqual(rc, 2, out)
        self.assertEqual(snapshot(self.depts), before)
        self.assertIn("01-director-of-crm-full-time-permanent -> 01-director-of-crm", out)

    def test_apply_meets_floor_keeps_howtos_and_is_idempotent(self):
        howto = (self.depts / "crm" / SUFFIXED[0] / "how-to.md").read_bytes()
        rc, out = self.run_it("--apply")
        self.assertEqual(rc, 0, out)
        crm = [p.name for p in (self.depts / "crm").iterdir() if p.is_dir()]
        self.assertFalse([n for n in crm if re.search(r"full-time|on-call|flagship", n)], crm)
        self.assertEqual({key(s) for s in INDEX["departments"]["crm"]["roles"]} - {key(n) for n in crm}, set())
        self.assertEqual((self.depts / "crm" / "01-director-of-crm" / "how-to.md").read_bytes(), howto)
        self.assertTrue((self.depts / "sales" / "03-closer-full-time-permanent").is_dir())
        self.assertIn("a folder for this library role already exists", out)
        after = snapshot(self.depts)
        rc, out = self.run_it("--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(self.depts), after, "second --apply must change nothing")

    def test_floor_departments_never_include_other_clients_lanes(self):
        rc, out = self.run_it("--add-floor-departments")
        gap = json.loads(out[:out.index("\n}\n") + 3])["gap"]
        self.assertTrue(set(gap) - {"crm", "sales"}, "no standard-floor department was proposed")
        self.assertFalse(set(gap) & set(OTHER_CLIENT), gap)


if __name__ == "__main__":
    unittest.main(verbosity=2)
