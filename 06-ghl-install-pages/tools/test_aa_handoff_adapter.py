#!/usr/bin/env python3
"""Tests for aa_handoff_adapter.py (Skill 06)."""
import hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aa_handoff_adapter as ada
class Test06(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp()); self.hd = self.td / "hi"; self.od = self.td / "out"
        self.hd.mkdir(parents=True)
    def _wf(self, *, alt=False, wrong_skill=False):
        cl = "Test_Client"; fn = f"Landing_Page-{cl}.md"
        (self.hd / fn).write_text("# Landing Page\n\nWelcome!\n", encoding="utf-8")
        sha = hashlib.sha256((self.hd / fn).read_bytes()).hexdigest()
        ho = {"handoff": "avatar-alchemist-downstream",
              "skill": "52-avatar-alchemist" if not wrong_skill else "99-other",
              "client_label": cl,
              "targets": [{"skill_number": 6,
                "inputs": [{"deliverable": "Landing_Page", "file": fn,
                             "sha256": sha if not alt else "0"*64}],
                "supporting": []}]}
        (self.hd / "HANDOFF.json").write_text(json.dumps(ho))
    def test_valid(self):
        self._wf(); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertEqual(vs, []); self.assertTrue((self.od / "page-manifest.json").is_file())
    def test_manifest_fields(self):
        self._wf(); ada.import_handoff(self.hd, self.od)
        pm = json.loads((self.od / "page-manifest.json").read_text())
        for f in ["display_name", "page_type", "steps"]: self.assertIn(f, pm)
        self.assertIn("ZHC", pm["display_name"])
    def test_content_copied(self):
        self._wf(); ada.import_handoff(self.hd, self.od)
        self.assertIn("Welcome!", (self.od / "landing-page-content.md").read_text())
    def test_checksum_fail(self):
        self._wf(alt=True); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIsNone(m); self.assertIn("AF-GHL-ADAPTER-CHECKSUM", {c for c,_ in vs})
    def test_no_handoff(self):
        (self.hd / "HANDOFF.json").unlink(missing_ok=True); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-GHL-ADAPTER-NO-HANDOFF", {c for c,_ in vs})
    def test_mutation_proof(self):
        self._wf(); vs, _ = ada.import_handoff(self.hd, self.od); self.assertEqual(vs, [])
        self._wf(alt=True); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-GHL-ADAPTER-CHECKSUM", {c for c,_ in vs})
    def test_constants(self):
        self.assertEqual(len(ada.REQUIRED), 1); self.assertNotEqual(ada.VERSION, "")
if __name__ == "__main__":
    unittest.main()
