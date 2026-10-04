#!/usr/bin/env python3
"""No-silent-stub installer rules (v25.4.0).

Covers Trevor's 5 installer rules:
  1. DIRECTOR REQUIRED — a department cannot complete without a director role;
     missing directors are scaffolded from the director template + flagged.
  2. NO SILENT PLACEHOLDERS — library miss => routing notice to general-task +
     machine-readable SOP-needed record; PENDING stubs are never written.
  3. SELF-HEALING — SOP-needed records feed author-missing-sops.py; authored
     SOPs upstream into templates/role-library/.
  4. DOCTRINE IN TEMPLATES — director templates carry the persistent/
     ephemeral pattern; the AI CEO template carries the chain of command with
     the {{AI_CEO_NAME}} config token (never hardcoded).
  5. NO EMPTY DEPARTMENTS + NO SCAFFOLD NOISE — zero-role departments refused;
     no <dept>/roles/how-to.md or <dept>/sops/how-to.md aggregate stubs.

Run: python3 tests/unit/test_no_silent_stubs.py
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S23 = ROOT / "23-ai-workforce-blueprint" / "scripts"
LIB = ROOT / "23-ai-workforce-blueprint" / "templates" / "role-library"
sys.path.insert(0, str(S23))

import create_role_workspaces as crw  # noqa: E402


class TestStubRemoved(unittest.TestCase):
    def test_stub_how_to_raises(self):
        with self.assertRaises(RuntimeError):
            crw.stub_how_to("X", "Y", False)


class TestRoutingDoc(unittest.TestCase):
    def setUp(self):
        self.doc = crw.routing_how_to(
            "Widget Analyst", "Marketing", "marketing", "Acme Co", "coaching",
            "sop-needed-0007", role_description="Analyzes widgets.")

    def test_substance_floor(self):
        self.assertGreaterEqual(len(self.doc.encode("utf-8")), 3072)

    def test_no_pending_markers(self):
        self.assertNotIn("PENDING - FILL FROM LIBRARY", self.doc)
        self.assertNotIn("PENDING — FILL FROM LIBRARY", self.doc)
        self.assertNotIn("how-to.md (stub)", self.doc)

    def test_routes_to_general_task(self):
        self.assertIn("general-task", self.doc)
        self.assertIn("sop-needed-0007", self.doc)

    def test_names_role_and_company(self):
        self.assertIn("Widget Analyst", self.doc)
        self.assertIn("Acme Co", self.doc)


class TestSopNeededRecords(unittest.TestCase):
    def setUp(self):
        crw.SOP_NEEDED_RECORDS.clear()

    def tearDown(self):
        crw.SOP_NEEDED_RECORDS.clear()

    def test_record_shape(self):
        rec = crw.record_sop_needed("Widget Analyst", "marketing",
                                    "no role-library template matched")
        self.assertEqual(rec["role"], "Widget Analyst")
        self.assertEqual(rec["department"], "marketing")
        self.assertEqual(rec["reason"], "no role-library template matched")
        self.assertEqual(rec["routed_to"], "general-task")
        self.assertEqual(rec["status"], "routed")
        self.assertTrue(rec["id"].startswith("sop-needed-"))
        self.assertIn("recorded_at", rec)

    def test_manifest_write_and_merge(self):
        with tempfile.TemporaryDirectory() as td:
            crw.record_sop_needed("Role A", "marketing", "no match")
            p1 = crw.write_sop_needed_manifest(td)
            data = json.loads(Path(p1).read_text())
            self.assertEqual(data["open_count"], 1)
            self.assertTrue((Path(td) / "SOP-NEEDED.md").is_file())
            # Mark authored, add another record, re-write: authored wins.
            data["records"][0]["status"] = "authored"
            Path(p1).write_text(json.dumps(data))
            crw.SOP_NEEDED_RECORDS.clear()
            crw.record_sop_needed("Role A", "marketing", "no match")
            crw.record_sop_needed("Role B", "sales", "no match")
            crw.write_sop_needed_manifest(td)
            data2 = json.loads(Path(p1).read_text())
            by_role = {r["role"]: r["status"] for r in data2["records"]}
            self.assertEqual(by_role["Role A"], "authored")  # never downgraded
            self.assertEqual(by_role["Role B"], "routed")
            self.assertEqual(data2["open_count"], 1)


class TestDirectorRequired(unittest.TestCase):
    def test_detects_director(self):
        self.assertTrue(crw._role_is_director({"name": "Director of CRM", "slug": "x"}))
        self.assertTrue(crw._role_is_director({"name": "Head of Sales", "slug": "head-of-sales"}))
        self.assertTrue(crw._role_is_director({"name": "Someone", "slug": "y", "number": 0}))
        self.assertFalse(crw._role_is_director({"name": "Writer", "slug": "writer", "number": 3}))

    def test_scaffold_when_missing(self):
        roles = crw.ensure_director_role(
            [{"name": "Writer", "slug": "writer", "number": 1}], "nosuchdept")
        self.assertEqual(len(roles), 2)
        d = roles[0]
        self.assertTrue(d["_scaffolded_director"])
        self.assertTrue(d["_needs_human_review"])
        self.assertEqual(d["number"], 0)
        self.assertIn("Director", d["name"])

    def test_no_scaffold_when_present(self):
        roles = [{"name": "Director of CRM", "slug": "director-of-crm", "number": 0},
                 {"name": "Writer", "slug": "writer", "number": 1}]
        out = crw.ensure_director_role(list(roles), "crm")
        self.assertEqual(len(out), 2)
        self.assertFalse(any(r.get("_scaffolded_director") for r in out))

    def test_empty_input_gets_director(self):
        out = crw.ensure_director_role([], "nosuchdept")
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["_scaffolded_director"])

    def test_instantiate_refuses_empty(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                crw.instantiate_department(str(Path(td) / "d"), "d", [], td)


class TestAiCeoToken(unittest.TestCase):
    def test_default_is_neutral(self):
        filled = crw.fill_tokens("Hello {{AI_CEO_NAME}}", "R", "D", True)
        self.assertIn("AI CEO", filled)
        self.assertNotIn("{{AI_CEO_NAME}}", filled)
        self.assertNotIn("Stephanie", filled)

    def test_no_hardcoded_ceo_name_in_templates(self):
        ceo = (LIB / "master-orchestrator" / "master-orchestrator.md").read_text()
        self.assertNotIn("Stephanie", ceo)
        self.assertIn("{{AI_CEO_NAME}}", ceo)


class TestDoctrineInTemplates(unittest.TestCase):
    def test_director_templates_carry_doctrine(self):
        files = sorted(LIB.glob("*/director-of-*.md")) + sorted(LIB.glob("*/head-of-*.md"))
        self.assertGreaterEqual(len(files), 15)
        missing = [str(f) for f in files
                   if "Director Operating Doctrine" not in f.read_text(encoding="utf-8")]
        self.assertEqual(missing, [], f"doctrine missing in: {missing}")

    def test_doctrine_content(self):
        sample = (LIB / "crm" / "director-of-crm.md").read_text(encoding="utf-8")
        self.assertIn("ephemeral", sample)
        self.assertIn("{{AI_CEO_NAME}}", sample)
        self.assertIn("never skip a level", sample.lower())

    def test_ai_ceo_chain_of_command(self):
        ceo = (LIB / "master-orchestrator" / "master-orchestrator.md").read_text(encoding="utf-8")
        self.assertIn("Chain of Command", ceo)
        self.assertIn("talk only to directors", ceo)

    def test_director_scaffold_exists_and_substantive(self):
        scaf = LIB / "_director-scaffold.md"
        self.assertTrue(scaf.is_file())
        self.assertGreaterEqual(len(scaf.read_bytes()), 3072)
        text = scaf.read_text(encoding="utf-8")
        self.assertIn("{{AI_CEO_NAME}}", text)
        self.assertNotIn("Stephanie", text)


class TestNoScaffoldNoise(unittest.TestCase):
    def test_no_aggregate_stub_writer(self):
        # No current installer code may generate <dept>/roles/how-to.md or
        # <dept>/sops/how-to.md aggregate stubs.
        hits = []
        for py in S23.glob("*.py"):
            src = py.read_text(encoding="utf-8", errors="replace")
            if re.search(r'''["']roles["']\s*,\s*["']how-to\.md["']''', src):
                hits.append(str(py))
            if re.search(r'''["']sops["']\s*,\s*["']how-to\.md["']''', src):
                hits.append(str(py))
        for sh in S23.glob("*.sh"):
            src = sh.read_text(encoding="utf-8", errors="replace")
            if "roles/how-to.md" in src or "sops/how-to.md" in src:
                hits.append(str(sh))
        self.assertEqual(hits, [], f"aggregate stub writers: {hits}")


class TestAuthorQc(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "author_missing_sops", str(S23 / "author-missing-sops.py"))
        ams = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ams)
        self.ams = ams

    def test_rejects_thin(self):
        ok, why = self.ams.qc_authored("short")
        self.assertFalse(ok)

    def test_rejects_boilerplate(self):
        ok, why = self.ams.qc_authored(
            "x" * 4000 + "\n[Step 1 - to be personalized]\n" + "y" * 100)
        self.assertFalse(ok)
        self.assertIn("boilerplate", why)

    def test_accepts_real_sop(self):
        body = "# SOP\n\n" + "\n".join(
            f"{i}. Do the thing with the specific tool and payload." for i in range(1, 12)
        )
        body += "\n" + "Detailed DMAIC procedure text. " * 200
        ok, why = self.ams.qc_authored(body)
        self.assertTrue(ok, why)


class TestFillPendingRetarget(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fill_pending_howtos", str(S23 / "fill-pending-howtos.py"))
        fph = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fph)
        self.fph = fph

    def test_is_routed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "how-to.md"
            p.write_text(crw.routing_how_to("R", "D", "d", "C", "i", "sop-needed-0001"))
            self.assertTrue(self.fph.is_routed(p))
            p.write_text("# Real SOP\n\n" + "x" * 4000)
            self.assertFalse(self.fph.is_routed(p))


if __name__ == "__main__":
    unittest.main(verbosity=2)
