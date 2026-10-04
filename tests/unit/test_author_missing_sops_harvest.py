#!/usr/bin/env python3
"""author-missing-sops.py must never write into the installed role library.

The authored playbook goes to the role's own how-to.md. A client-neutral token
draft + a machine-readable SOP-NEEDED record go to the NEW collection folder
<OpenClaw root>/workforce/sop-harvest/. templates/role-library/ and its
_index.json stay byte-identical, so the update content check stays green.

Run: python3 tests/unit/test_author_missing_sops_harvest.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
S23 = ROOT / "23-ai-workforce-blueprint" / "scripts"
LIB = ROOT / "23-ai-workforce-blueprint" / "templates" / "role-library"
ROUTED = "[ROUTED — WORK HANDLED BY GENERAL-TASK]"


def snapshot(path):
    """(relative path, size, mtime_ns) for every file under path."""
    return sorted(
        (str(p.relative_to(path)), p.stat().st_size, p.stat().st_mtime_ns)
        for p in path.rglob("*") if p.is_file())


def sop_body(extra=""):
    body = "# {{ROLE_TITLE}} SOP for {{COMPANY_NAME}}\n\n" + "\n".join(
        f"{i}. Open the named input file and record the specific result." for i in range(1, 13))
    return body + "\n" + "Detailed DMAIC procedure text. " * 200 + extra


class HarvestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / ".openclaw"
        (self.root / "workspace").mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"HOME": str(self.home), "OPENCLAW_PLATFORM": "mac"})
        env.start()
        self.addCleanup(env.stop)
        sys.path.insert(0, str(S23))
        spec = importlib.util.spec_from_file_location(
            "author_missing_sops_harvest_under_test", str(S23 / "author-missing-sops.py"))
        self.ams = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ams)
        self.cfg = {"companyName": "Acme Widgets", "ownerName": "Pat Example",
                    "aiCeoName": "Orion"}
        for target, value in (("get_openclaw_paths", lambda: {"root": self.root}),
                              ("_load_company_config", lambda: self.cfg)):
            p = mock.patch.object(self.ams.crw, target, value)
            p.start()
            self.addCleanup(p.stop)

    def record(self, how_to=None):
        return {"id": "sop-needed-0001", "role": "Claims Auditor", "department": "finance",
                "how_to_path": str(how_to) if how_to else "", "status": "routed"}

    def harvest(self):
        return self.root / "workforce" / "sop-harvest"


class TestHarvest(HarvestCase):
    def test_writes_draft_and_record_only_under_sop_harvest(self):
        ok, why = self.ams.upstream_to_library(self.record(), sop_body())
        self.assertTrue(ok, why)
        files = sorted(p.name for p in self.harvest().rglob("*") if p.is_file())
        self.assertEqual(len(files), 2, files)
        self.assertTrue(any(f.endswith(".draft.md") for f in files))
        rec_file = next(self.harvest().rglob("*.sop-needed.json"))
        rec = json.loads(rec_file.read_text())
        self.assertEqual(rec["status"], "SOP-NEEDED")
        self.assertEqual(rec["department"], "finance")
        self.assertEqual(rec["role_slug"], "claims-auditor")
        self.assertTrue(rec["content_sha"].startswith("sha256:"))
        self.assertGreaterEqual(rec["bytes"], self.ams.MIN_BYTES)

    def test_draft_is_client_neutral(self):
        leaky = sop_body("\nAsk Pat Example and Orion about Acme Widgets pricing.\n")
        self.assertTrue(self.ams.upstream_to_library(self.record(), leaky)[0])
        draft = next(self.harvest().rglob("*.draft.md")).read_text()
        for literal in ("Acme Widgets", "Pat Example", "Orion"):
            self.assertNotIn(literal, draft)
        for token in ("{{COMPANY_NAME}}", "{{OWNER_NAME}}", "{{AI_CEO_NAME}}"):
            self.assertIn(token, draft)

    def test_rerun_same_content_is_idempotent(self):
        self.assertTrue(self.ams.upstream_to_library(self.record(), sop_body())[0])
        before = snapshot(self.harvest())
        ok, why = self.ams.upstream_to_library(self.record(), sop_body())
        self.assertTrue(ok, why)
        self.assertEqual(snapshot(self.harvest()), before)

    def test_different_content_never_overwrites_earlier_draft(self):
        self.assertTrue(self.ams.upstream_to_library(self.record(), sop_body())[0])
        self.assertTrue(self.ams.upstream_to_library(self.record(), sop_body("\nExtra.\n"))[0])
        self.assertEqual(len(list(self.harvest().rglob("*.draft.md"))), 2)

    def test_no_openclaw_root_fails_closed(self):
        with mock.patch.object(self.ams.crw, "get_openclaw_paths", lambda: {"root": None}):
            ok, why = self.ams.upstream_to_library(self.record(), sop_body())
        self.assertFalse(ok)
        self.assertIn("nothing harvested", why)


class TestLibraryUntouched(HarvestCase):
    def test_finalize_leaves_installed_library_and_content_check_green(self):
        lib_before = snapshot(LIB)
        check = [sys.executable, str(S23 / "hash-content-manifest.py"), "--check"]
        pre = subprocess.run(check, capture_output=True, text=True)
        self.assertEqual(pre.returncode, 0, pre.stdout + pre.stderr)

        how_to = self.home / "role" / "how-to.md"
        how_to.parent.mkdir()
        how_to.write_text(f"# Claims Auditor — how-to.md  {ROUTED}\n")
        data = {"records": [self.record(how_to)]}
        manifest = self.home / "SOP-NEEDED.json"
        manifest.write_text(json.dumps(data))
        # Point the library resolver at the real repo library: if the script
        # still wrote there, the snapshot below would differ.
        with mock.patch.object(self.ams.crw, "_resolve_skill_dir", lambda: LIB.parent.parent):
            ok, why = self.ams.finalize_record(data["records"][0], sop_body(), manifest, data)
        self.assertTrue(ok, why)

        self.assertEqual(snapshot(LIB), lib_before)
        post = subprocess.run(check, capture_output=True, text=True)
        self.assertEqual(post.returncode, 0, post.stdout + post.stderr)
        self.assertNotIn(ROUTED, how_to.read_text())
        self.assertIn("source=role-library-authored", how_to.read_text())
        self.assertEqual(json.loads(manifest.read_text())["records"][0]["status"], "authored")
        self.assertEqual(len(list(self.harvest().rglob("*.draft.md"))), 1)

    def test_harvest_failure_does_not_undo_authored_how_to(self):
        how_to = self.home / "role" / "how-to.md"
        how_to.parent.mkdir()
        how_to.write_text(f"# Claims Auditor {ROUTED}\n")
        data = {"records": [self.record(how_to)]}
        manifest = self.home / "SOP-NEEDED.json"
        manifest.write_text(json.dumps(data))
        with mock.patch.object(self.ams, "harvest_dir", lambda: None):
            ok, why = self.ams.finalize_record(data["records"][0], sop_body(), manifest, data)
        self.assertTrue(ok, why)
        self.assertEqual(data["records"][0]["status"], "authored")
        self.assertIn("skipped", data["records"][0]["harvest"])

    def test_script_has_no_library_write_path(self):
        src = (S23 / "author-missing-sops.py").read_text(encoding="utf-8")
        self.assertNotIn("_index.json\"", src.split("def upstream_to_library")[1].split("def author_one_subagent")[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
