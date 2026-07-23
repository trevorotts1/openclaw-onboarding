#!/usr/bin/env python3
"""Tests for aa_handoff_adapter.py (Skill 47)."""
import hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aa_handoff_adapter as ada

class Test47(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.hd = self.td / "hi"; self.od = self.td / "out"
        self.hd.mkdir(parents=True)

    def _wf(self, *, alt="", wrong_skill=False):
        cl = "Test_Client"
        for b, c in [("Top_39_Suggested_Image_Prompts", "## Prompt 1\nSunset over city\n## Prompt 2\nProduct hero shot\n"),
                      ("Landing_Page_Image_Prompts", "## LP Prompt\nBrand logo centered\n")]:
            fn = f"{b}-{cl}.md"; (self.hd / fn).write_text(c, encoding="utf-8")
        ho = {"handoff": "avatar-alchemist-downstream",
              "skill": "52-avatar-alchemist" if not wrong_skill else "99-other",
              "client_label": cl,
              "targets": [{"skill_number": 47,
                "inputs": [{"deliverable": b, "file": f"{b}-{cl}.md",
                             "sha256": hashlib.sha256((self.hd / f"{b}-{cl}.md").read_bytes()).hexdigest()
                                  if alt != b else "0"*64} for b in ada.REQUIRED],
                "supporting": []}]}
        (self.hd / "HANDOFF.json").write_text(json.dumps(ho))

    def test_valid(self):
        self._wf(); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertEqual(vs, []); self.assertTrue((self.od / "job-manifest.json").is_file())

    def test_jm_fields(self):
        self._wf(); ada.import_handoff(self.hd, self.od)
        jm = json.loads((self.od / "job-manifest.json").read_text())
        for f in ["job_id", "topic", "aspect_ratio", "pipeline_selected"]:
            self.assertIn(f, jm)

    def test_prompts_parsed(self):
        self._wf(); ada.import_handoff(self.hd, self.od)
        ip = json.loads((self.od / "image-prompts.json").read_text())
        self.assertGreater(ip["total_prompts"], 0)

    def test_checksum_fail(self):
        self._wf(alt="Top_39_Suggested_Image_Prompts"); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIsNone(m); self.assertIn("AF-VID-ADAPTER-CHECKSUM", {c for c,_ in vs})

    def test_no_handoff(self):
        (self.hd / "HANDOFF.json").unlink(missing_ok=True)
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-VID-ADAPTER-NO-HANDOFF", {c for c,_ in vs})

    def test_wrong_skill(self):
        self._wf(wrong_skill=True); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-VID-ADAPTER-WRONG-SKILL", {c for c,_ in vs})

    def test_mutation_proof(self):
        self._wf(); vs, _ = ada.import_handoff(self.hd, self.od)
        self.assertEqual(vs, [])
        self._wf(alt="Landing_Page_Image_Prompts")
        vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-VID-ADAPTER-CHECKSUM", {c for c,_ in vs})

    def test_constants(self):
        self.assertEqual(len(ada.REQUIRED), 2); self.assertNotEqual(ada.VERSION, "")

if __name__ == "__main__":
    unittest.main()
