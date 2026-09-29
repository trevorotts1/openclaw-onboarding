#!/usr/bin/env python3
"""PENDING role how-to.md files get picked up.

  * populate-sops-from-manifest.py: a department whose manifest lists
    sop_files=[] but whose roles are PENDING how-to.md stubs (vertical-pack
    departments) is QUEUED, not skipped as "already authored"; --dept restricts
    the run and --force re-queues an authored department.
  * fill-pending-howtos.py: token-fills a PENDING how-to.md from the nearest
    comparable role-library template, leaves roles with no comparable template
    PENDING (never a loose cross-department match), never touches a filled
    how-to.md, is a no-op on dry run and idempotent on --apply.

Run: python3 tests/unit/test_pending_sops_runner.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S23 = ROOT / "23-ai-workforce-blueprint" / "scripts"
POPULATE = S23 / "populate-sops-from-manifest.py"
FILL = S23 / "fill-pending-howtos.py"

PENDING = ("# {title} - how-to.md  [PENDING - FILL FROM LIBRARY]\n\n"
           "**Status:** PENDING - no role-library template matched this role.\n")


class _Box(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.home = Path(self._t.name)
        (self.home / ".openclaw" / "workspace").mkdir(parents=True)
        self.depts = self.home / "company" / "departments"
        self.env = dict(os.environ, HOME=str(self.home), OPENCLAW_PLATFORM="mac", PATH="/usr/bin:/bin")

    def tearDown(self):
        self._t.cleanup()

    def role(self, dept, folder, title=None, body=None):
        d = self.depts / dept / folder
        d.mkdir(parents=True)
        (d / "how-to.md").write_text(body if body is not None else PENDING.format(title=title))
        return d / "how-to.md"


class TestPopulateQueuesPendingDepartments(_Box):
    def manifest(self, depts):
        m = self.home / "company" / "sop-research-manifest.json"
        entries = [{"dept_id": d, "dept_name": d.title(), "dept_head": "Head", "dept_dir": str(self.depts / d),
                    "company_name": "Fixture Co", "industry": "real estate", "department_kpis": "",
                    "department_tools": "", "sop_files": []} for d in depts]
        m.write_text(json.dumps({"departments": entries, "company": "Fixture Co",
                                 "sub_agent_instructions": "Write SOPs for {DEPT_NAME} at {DEPT_DIR}"}))
        return m

    def run_populate(self, *args):
        return subprocess.run([sys.executable, str(POPULATE), *map(str, args)], capture_output=True,
                              text=True, env=self.env, timeout=120)

    def test_empty_sop_files_with_pending_roles_is_queued(self):
        self.role("lead-generation", "01-lead-generation-specialist", "Lead Generation Specialist")
        r = self.run_populate("--manifest", self.manifest(["lead-generation"]), "--dry-run")
        out = r.stdout + r.stderr
        self.assertNotIn("SKIP lead-generation", out)
        self.assertIn("dept lead-generation would get 1 SOPs populated", out, out)

    def test_dept_filter_and_force(self):
        self.role("lead-generation", "01-lead-generation-specialist", "Lead Generation Specialist")
        self.role("showings", "01-showing-coordinator", body="# Showing Coordinator\n\n" + "Real SOP content.\n" * 40)
        m = self.manifest(["lead-generation", "showings"])
        out = (lambda r: r.stdout + r.stderr)(self.run_populate("--manifest", m, "--dry-run", "--dept", "showings"))
        self.assertNotIn("lead-generation", out.split("Spawn mode")[-1])
        self.assertIn("SKIP showings", out)  # nothing pending, nothing listed: already done
        r = self.run_populate("--manifest", m, "--dry-run", "--dept", "nope")
        self.assertEqual(r.returncode, 1)
        (self.depts / "showings" / "01-showing-coordinator" / "01-intake.md").write_text("x" * 400)
        m2 = json.loads(m.read_text())
        m2["departments"][1]["sop_files"] = [{"role_folder": "01-showing-coordinator", "sop_file": "01-intake.md",
                                              "role_dir": str(self.depts / "showings" / "01-showing-coordinator")}]
        m.write_text(json.dumps(m2))
        out = (lambda r: r.stdout + r.stderr)(self.run_populate("--manifest", m, "--dry-run", "--dept", "showings", "--force"))
        self.assertIn("dept showings would get 1 SOPs populated", out, out)


class TestFillRunner(_Box):
    def fill(self, *args):
        return subprocess.run([sys.executable, str(FILL), "--departments-dir", str(self.depts), *args],
                              capture_output=True, text=True, env=self.env, timeout=120)

    def test_fills_comparable_leaves_others_pending(self):
        fillable = self.role("marketing", "07-senior-copywriter", "Senior Copywriter")
        stranger = self.role("showings", "01-buyer-agent", "Buyer Agent")
        done = self.role("marketing", "01-cmo", body="# CMO how-to\n\nOwner-written content.\n")
        before = {p: p.read_bytes() for p in (fillable, stranger, done)}
        r = self.fill()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(before, {p: p.read_bytes() for p in before}, "dry run must not write")
        r = self.fill("--apply")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        text = fillable.read_text()
        self.assertNotIn("PENDING - FILL FROM LIBRARY", text)
        self.assertIn("generator=fill-pending-howtos.py", text)
        self.assertGreaterEqual(len(text.encode()), 3072)
        self.assertEqual(stranger.read_bytes(), before[stranger], "no comparable template: stays PENDING")
        self.assertEqual(done.read_bytes(), before[done], "a filled how-to.md is never touched")
        after = {p: p.read_bytes() for p in before}
        self.fill("--apply")
        self.assertEqual(after, {p: p.read_bytes() for p in before}, "second --apply is a no-op")


if __name__ == "__main__":
    unittest.main(verbosity=2)
