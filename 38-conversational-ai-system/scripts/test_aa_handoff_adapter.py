#!/usr/bin/env python3
"""Tests for aa_handoff_adapter.py (Skill 38)."""
import hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aa_handoff_adapter as ada
class Test38(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp()); self.hd = self.td / "hi"; self.od = self.td / "out"
        self.hd.mkdir(parents=True)
    def _wf(self, *, alt="", wrong_skill=False, with_sup=False):
        cl = "Test_Client"
        cts = {"AI_Booking_Bot_Intelligence": "## persona\nBooking assistant\n## goal\nBook\n## greeting\nHello!\n## booking\nCheck avail\n",
               "AI_Post_Booking_Bot_Intelligence": "## persona\nPost-booking bot\n## goal\nConfirm\n## greeting\nThanks!\n",
               "Rescheduling_Booking_Bot_Intelligence": "## persona\nReschedule bot\n## goal\nReschedule\n## greeting\nHelp!\n",
               "AI_Bot_Prep_Doc_Intelligence": "## persona\nPrep assistant\n## goal\nPrep\n"}
        for b in ada.REQUIRED:
            (self.hd / f"{b}-{cl}.md").write_text(cts[b], encoding="utf-8")
        if with_sup:
            for b in ada.SUPPORTING:
                (self.hd / f"{b}-{cl}.md").write_text(cts[b], encoding="utf-8")
        inp = [{"deliverable": b, "file": f"{b}-{cl}.md",
                 "sha256": hashlib.sha256((self.hd / f"{b}-{cl}.md").read_bytes()).hexdigest()
                      if alt != b else "0"*64} for b in ada.REQUIRED]
        sup = []
        if with_sup:
            sup = [{"deliverable": b, "file": f"{b}-{cl}.md",
                     "sha256": hashlib.sha256((self.hd / f"{b}-{cl}.md").read_bytes()).hexdigest()
                          if alt != b else "0"*64} for b in ada.SUPPORTING]
        ho = {"handoff": "avatar-alchemist-downstream",
              "skill": "52-avatar-alchemist" if not wrong_skill else "99-other",
              "client_label": cl,
              "targets": [{"skill_number": 38, "inputs": inp, "supporting": sup}]}
        (self.hd / "HANDOFF.json").write_text(json.dumps(ho))
    def test_valid(self):
        self._wf(); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertEqual(vs, []); self.assertTrue((self.od / "conversation-playbooks.json").is_file())
    def test_playbook_fields(self):
        self._wf(); ada.import_handoff(self.hd, self.od)
        cp = json.loads((self.od / "conversation-playbooks.json").read_text())
        self.assertEqual(cp["playbook_count"], 3)
        for pb in cp["playbooks"]:
            for f in ["persona", "goal", "phases"]: self.assertIn(f, pb)
            self.assertEqual(len(pb["phases"]), 4)
    def test_intake(self):
        self._wf(); ada.import_handoff(self.hd, self.od)
        bi = json.loads((self.od / "booking-bot-intake.json").read_text())
        self.assertEqual(len(bi["required_docs"]), 3)
    def test_with_supporting(self):
        self._wf(with_sup=True); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertEqual(vs, [])
    def test_checksum_fail(self):
        self._wf(alt="AI_Booking_Bot_Intelligence"); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIsNone(m); self.assertIn("AF-CONV-ADAPTER-CHECKSUM", {c for c,_ in vs})
    def test_no_handoff(self):
        (self.hd / "HANDOFF.json").unlink(missing_ok=True); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-CONV-ADAPTER-NO-HANDOFF", {c for c,_ in vs})
    def test_wrong_skill(self):
        self._wf(wrong_skill=True); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-CONV-ADAPTER-WRONG-SKILL", {c for c,_ in vs})
    def test_mutation_proof(self):
        self._wf(); vs, _ = ada.import_handoff(self.hd, self.od); self.assertEqual(vs, [])
        self._wf(alt="AI_Post_Booking_Bot_Intelligence"); vs, m = ada.import_handoff(self.hd, self.od)
        self.assertIn("AF-CONV-ADAPTER-CHECKSUM", {c for c,_ in vs})
    def test_constants(self):
        self.assertEqual(len(ada.REQUIRED), 3); self.assertEqual(len(ada.SUPPORTING), 1)
        self.assertNotEqual(ada.VERSION, "")
if __name__ == "__main__":
    unittest.main()
