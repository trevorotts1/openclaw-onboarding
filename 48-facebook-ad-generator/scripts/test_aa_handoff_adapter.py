#!/usr/bin/env python3
"""Tests for aa_handoff_adapter.py (Skill 48)."""
import hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aa_handoff_adapter as ada

class Test48(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.hd = self.td / "hi"; self.od = self.td / "out"
        self.hd.mkdir(parents=True)

    def _wf(self, *, alt="", wrong_skill=False):
        cl = "Test_Client"
        contents = [("Top_39_Suggested_Ad_Angles", "# Ad Angles\n1. First angle\n2. Second\n"),
                     ("Facebook_Headline_and_Primary_Text_Ad_Copy_Writer", "# Headlines\nHeadline: Buy\n\n# Primary Text\nGet it.\n"),
                     ("Facebook_Targeting_Intelligence", "# Audience\n- Business owners\n- Marketers\n")]
        for b, c in contents:
            fn = f"{b}-{cl}.md"; (self.hd / fn).write_text(c, encoding="utf-8")
        ho = {"handoff": "avatar-alchemist-downstream",
              "skill": "52-avatar-alchemist" if not wrong_skill else "99-other",
              "client_label": cl,
              "targets": [{"skill_number": 48,
                "inputs": [{"deliverable": b, "file": f"{b}-{cl}.md",
                             "sha256": hashlib.sha256((self.hd / f"{b}-{cl}.md").read_bytes()).hexdigest()
                                  if alt != b else "0"*64} for b in ada.REQUIRED],
                "supporting": []}]}
        (self.hd / "HANDOFF.json").write_text(json.dumps(ho))

    def test_valid(self):
        self._wf(); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertEqual(vs, []); self.assertEqual(len(m), 3)

    def test_checksum_fail(self):
        self._wf(alt="Top_39_Suggested_Ad_Angles"); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIsNone(m); self.assertIn("AF-FBAD-ADAPTER-CHECKSUM", {c for c,_ in vs})

    def test_missing_file(self):
        self._wf()
        ho = json.loads((self.hd / "HANDOFF.json").read_text())
        ho["targets"][0]["inputs"][0]["file"] = "gone.md"
        (self.hd / "HANDOFF.json").write_text(json.dumps(ho))
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-FBAD-ADAPTER-MISSING", {c for c,_ in vs})

    def test_no_handoff(self):
        (self.hd / "HANDOFF.json").unlink(missing_ok=True)
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-FBAD-ADAPTER-NO-HANDOFF", {c for c,_ in vs})

    def test_wrong_type(self):
        (self.hd / "HANDOFF.json").write_text(json.dumps({"handoff": "other", "skill": "52", "targets": []}))
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-FBAD-ADAPTER-NOT-HANDOFF", {c for c,_ in vs})

    def test_wrong_skill(self):
        self._wf(wrong_skill=True)
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-FBAD-ADAPTER-WRONG-SKILL", {c for c,_ in vs})

    def test_no_target(self):
        (self.hd / "HANDOFF.json").write_text(json.dumps({"handoff": "avatar-alchemist-downstream", "skill": "52-avatar-alchemist", "client_label": "T", "targets": []}))
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-FBAD-ADAPTER-NO-TARGET", {c for c,_ in vs})

    def test_bad_json(self):
        (self.hd / "HANDOFF.json").write_text("not json {{{")
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-FBAD-ADAPTER-PARSE", {c for c,_ in vs})

    def test_mutation_proof(self):
        self._wf(); vs, _ = ada.import_handoff(self.hd, self.od)
        self.assertEqual(vs, [])
        self._wf(alt="Facebook_Headline_and_Primary_Text_Ad_Copy_Writer")
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIsNone(m)
        self.assertIn("AF-FBAD-ADAPTER-CHECKSUM", {c for c,_ in vs})

    def test_constants(self):
        self.assertEqual(len(ada.REQUIRED), 3); self.assertNotEqual(ada.VERSION, "")

if __name__ == "__main__":
    unittest.main()
