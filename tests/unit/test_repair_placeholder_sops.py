#!/usr/bin/env python3
"""repair-placeholder-sops.py: placeholder how-to.md files on an existing box get repaired.

Proves: every legacy stub shape is detected; a library-matched role is filled
(>= 3072 bytes, no stub marker left); a role with no template is handed to the
authoring path (ROUTED notice + open SOP-NEEDED.json record, never a guess);
aggregate department-level stubs are deleted; real content is never touched, even
under a stub-looking mention; dry run writes nothing; a second run changes nothing;
openclaw.json is never touched.

Run: python3 tests/unit/test_repair_placeholder_sops.py
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "23-ai-workforce-blueprint" / "scripts" / "repair" / "repair-placeholder-sops.py"

STUB_HYPHEN = ("# {t} - how-to.md  [PENDING - FILL FROM LIBRARY]\n\n"
               "**Status:** PENDING - no role-library template matched this role.\n")
STUB_ORIGINAL = ("# {t} — how-to.md (stub)  [PENDING — FILL FROM LIBRARY]\n\n**Department:** X\n"
                 "**Status:** PENDING — no pre-written library doc matched this role.\n\n"
                 "## 1. Role Identity\n\n### Who You Are\n{t} in X.\n\n### What This Role Is NOT\n"
                 "(Pending fill — see the one-shot instruction above.)\n\n## 2. Persona Governance Override\n"
                 "Defer to the governing persona.\n\n## 3-19. Pending fill — read the one-shot instruction.\n")
STUB_OWNER = ("# {t} - how-to.md  [PENDING - OWNER-REQUESTED CUSTOM ROLE - FILL FROM LIBRARY]\n\n"
              "**Owner request:** Handle the quarterly vendor audit for the owner.\n"
              "**Status:** PENDING - owner-requested custom role.\n\n## What This Role Does\n\n"
              "Handle the quarterly vendor audit for the owner.\n")
STUB_ADDROLE = ("# {t} — how-to.md (stub)  [PENDING — FILL FROM LIBRARY]\n\n**Department:** x\n"
                "**Status:** PENDING — fill this file with the role's SOPs before assigning work.\n\n"
                "## Quick-start\n1. Read IDENTITY.md to understand who this role is.\n"
                "2. Read SOUL.md to understand the mission and values.\n\n## Responsibilities\n"
                "(Fill from role-library template or write from interview)\n")
REAL = "# {t} how-to\n\n" + "Real owner-written procedure step.\n" * 200


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class _Box(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.home = Path(self._t.name)
        (self.home / ".openclaw" / "workspace").mkdir(parents=True)
        self.company = self.home / "company"
        self.depts = self.company / "departments"
        self.env = dict(os.environ, HOME=str(self.home), OPENCLAW_PLATFORM="mac", PATH="/usr/bin:/bin",
                        PYTHONDONTWRITEBYTECODE="1")  # keep the interpreter's own cache out of the box
        self.cfg = self.home / ".openclaw" / "openclaw.json"
        self.cfg.write_text('{"agents":{"defaults":{"model":"x/y"}}}')
        self.cfg_sha = sha(self.cfg)

    def tearDown(self):
        self._t.cleanup()

    def put(self, dept, folder, body):
        d = self.depts / dept / folder if folder else self.depts / dept
        d.mkdir(parents=True, exist_ok=True)
        (d / "how-to.md").write_text(body)
        return d / "how-to.md"

    def run_repair(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--departments-dir", str(self.depts), *args],
                              capture_output=True, text=True, env=self.env, timeout=180)

    def manifest(self):
        return json.loads((self.company / "SOP-NEEDED.json").read_text())

    def snapshot(self):
        return {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}


class TestRepairPlaceholderSops(_Box):
    def fixture(self):
        f = {
            "fill_hyphen": self.put("marketing", "07-senior-copywriter", STUB_HYPHEN.format(t="Senior Copywriter")),
            "no_template": self.put("showings", "01-buyer-agent", STUB_ORIGINAL.format(t="Buyer Agent")),
            "owner": self.put("showings", "02-vendor-auditor", STUB_OWNER.format(t="Vendor Auditor")),
            "addrole": self.put("showings", "03-zzq-wrangler", STUB_ADDROLE.format(t="Zzq Wrangler")),
            "real": self.put("marketing", "01-cmo", REAL.format(t="CMO")),
            "mention": self.put("marketing", "02-notes",
                                "# Notes how-to\n\nOld stubs said FILL FROM LIBRARY in their title.\n" + "Real line.\n" * 300),
            "thin_real": self.put("marketing", "03-thin", STUB_HYPHEN.format(t="Thin") + "Owner wrote this.\n" * 40),
            "dept_stub": self.put("showings", None, STUB_ORIGINAL.format(t="Showings")),
            "sops_stub": self.put("showings", "sops", STUB_HYPHEN.format(t="Showings Sops")),
        }
        return f

    def test_apply_repairs_and_protects(self):
        f = self.fixture()
        real_before = {k: f[k].read_bytes() for k in ("real", "mention", "thin_real")}
        r = self.run_repair("--json")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)  # roles still need authoring + one manual review
        counts = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(counts["aggregate_stubs_deleted"], 2, counts)
        self.assertEqual(counts["needs_manual_review"], 1, counts)
        self.assertEqual(counts["errors"], 0, counts)
        # library fill: real content, floor met, signature gone, provenance stamped
        text = f["fill_hyphen"].read_text()
        self.assertGreaterEqual(len(text.encode()), 3072)
        self.assertNotIn("FILL FROM LIBRARY", text)
        self.assertIn("generator=repair-placeholder-sops.py", text)
        # no template: ROUTED notice + open record; the model is never chosen here
        recs = {x["role"]: x for x in self.manifest()["records"]}
        self.assertIn("[ROUTED — WORK HANDLED BY GENERAL-TASK]", f["no_template"].read_text())
        self.assertEqual(recs["Buyer Agent"]["status"], "routed")
        self.assertIn("quarterly vendor audit", recs["Vendor Auditor"]["role_description"])
        self.assertIn("quarterly vendor audit", f["owner"].read_text())  # owner's words survive
        self.assertNotIn("FILL FROM LIBRARY", f["addrole"].read_text())
        # aggregate stubs gone, aggregate-free departments keep their roles
        self.assertFalse(f["dept_stub"].exists())
        self.assertFalse(f["sops_stub"].exists())
        # real content and look-alikes untouched
        for k, v in real_before.items():
            self.assertEqual(f[k].read_bytes(), v, k)
        self.assertEqual(sha(self.cfg), self.cfg_sha, "openclaw.json must never change")

    def test_dry_run_writes_nothing(self):
        self.fixture()
        before = self.snapshot()
        r = self.run_repair("--dry-run")
        self.assertIn("DRY RUN", r.stdout)
        self.assertIn("WOULD FILL", r.stdout)
        self.assertEqual(before, self.snapshot())

    def test_idempotent(self):
        self.fixture()
        self.run_repair()
        after_first = self.snapshot()
        r = self.run_repair("--json")
        counts = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(counts["filled_from_library"] + counts["handed_to_authoring"]
                         + counts["aggregate_stubs_deleted"], 0, counts)
        self.assertEqual(after_first, self.snapshot(), "second run must change nothing")

    def test_clean_box_exits_zero(self):
        self.put("marketing", "01-cmo", REAL.format(t="CMO"))
        r = self.run_repair()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_symlinked_how_to_never_touched(self):
        target = self.home / "shared-stub.md"
        target.write_text(STUB_HYPHEN.format(t="Shared"))
        d = self.depts / "marketing" / "04-shared"
        d.mkdir(parents=True)
        (d / "how-to.md").symlink_to(target)
        self.run_repair()
        self.assertTrue((d / "how-to.md").is_symlink())
        self.assertEqual(target.read_text(), STUB_HYPHEN.format(t="Shared"))

    def test_missing_departments_dir(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--departments-dir", str(self.home / "nope")],
                           capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
