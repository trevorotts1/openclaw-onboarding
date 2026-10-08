#!/usr/bin/env python3
"""H12 tests: a master must come from the skill assembler, not a hand script.

  PASS: a clean run folder + a master vouched for by an assembler receipt.
  FAIL: run folder with edit/final.py that calls ffmpeg directly.
  FAIL: a caption script (writes .srt) in the run folder.
  FAIL: no receipt / receipt from another module / swapped master.
  WIRE: assemble() writes produced_by + master_sha256 (fake ffmpeg).
  GATE: the FAIL record is accepted-as-FAIL by qc_gate (final_edit).
Run: python3 core/final_assembler/test_master_provenance_h12.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import qc_gate as G                                      # noqa: E402
import final_assembler.assembler as A                    # noqa: E402
from final_assembler import master_provenance as M      # noqa: E402

REV = {"identity": "qc-bot", "session": "s1", "authority": "qc"}


def _run(tmp, scripts=None, receipt="good"):
    """Build a run folder; return master path."""
    os.makedirs(os.path.join(tmp, "edit"))
    master = os.path.join(tmp, "master.mp4")
    with open(master, "wb") as f:
        f.write(b"fake-master-bytes")
    for rel, body in (scripts or {}).items():
        with open(os.path.join(tmp, rel), "w") as f:
            f.write(body)
    if receipt:
        rc = {"outcome": "ok", "produced_by": M.producer_stamp(),
              "master_sha256": M.sha256_file(master)}
        if receipt == "other":
            rc["produced_by"] = {"module": "edit.final"}
        if receipt == "swapped":
            rc["master_sha256"] = "0" * 64
        with open(master + ".receipt.json", "w") as f:
            json.dump(rc, f)
    return master


class T(unittest.TestCase):
    def check(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            master = _run(tmp, **kw)
            return M.check_master_provenance(tmp, master)

    def test_clean_pass(self):
        r = self.check(scripts={"edit/notes.py": "print('hi')"})
        self.assertTrue(r["pass"], r)

    def test_edit_final_py_with_ffmpeg_fails(self):
        r = self.check(scripts={"edit/final.py":
                                "subprocess.run(['ffmpeg','-r','24'])"})
        self.assertFalse(r["pass"])
        self.assertEqual(r["reason_code"], M.NON_SKILL_SCRIPT)
        self.assertEqual(r["evidence"]["scripts"], ["edit/final.py"])

    def test_caption_script_fails(self):
        r = self.check(scripts={"edit/caps.sh": "echo x > out.srt"})
        self.assertEqual(r["reason_code"], M.NON_SKILL_SCRIPT)

    def test_receipt_cases(self):
        self.assertEqual(self.check(receipt=None)["reason_code"],
                         M.RECEIPT_MISSING)
        self.assertEqual(self.check(receipt="other")["reason_code"],
                         M.NOT_SKILL_MODULE)
        self.assertEqual(self.check(receipt="swapped")["reason_code"],
                         M.MASTER_HASH_MISMATCH)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "needs real ffmpeg/ffprobe (tiny 64x64 render)")
    def test_assembler_receipt_carries_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = os.path.join(tmp, "c.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-threads", "2", "-f",
                            "lavfi", "-i", "testsrc=s=64x64:r=30:d=1.6",
                            "-pix_fmt", "yuv420p", clip], check=True)
            tl = os.path.join(tmp, "timeline.json")
            with open(tl, "w") as f:
                json.dump({"schema_version": "blackceo.timeline/v1",
                           "fps": 30, "width": 64, "height": 64,
                           "song_path": None, "transition": "none",
                           "segments": [{"src": "c.mp4", "dur": 1.5,
                                         "motion_score": 0.9,
                                         "beat_cut": True,
                                         "lip_sync": True}] * 3}, f)
            out = os.path.join(tmp, "master.mp4")
            rc = A.assemble(tl, out)
            self.assertEqual(rc["outcome"], "ok", rc)
            self.assertEqual(rc["produced_by"], M.producer_stamp())
            self.assertEqual(rc["master_sha256"], M.sha256_file(out))
            self.assertTrue(M.check_master_provenance(tmp, out)["pass"])

    def test_qc_gate_rejects_fail_record(self):
        res = self.check(scripts={"edit/final.py": "ffmpeg"})
        rec = M.to_qc_record(res, "run1", "final", REV)
        out = G.evaluate("run1", "final", [rec], {"master-provenance": "builder"},
                         ["final_edit"], master={"chosen_length_s": 60, "measured_s": 58})
        self.assertEqual(out["gate"], "FAIL")
        ok = M.to_qc_record({"pass": True, "evidence": {"summary": "ok"}},
                            "run1", "final", REV)
        out = G.evaluate("run1", "final", [ok], {"master-provenance": "builder"},
                         ["final_edit"], master={"chosen_length_s": 60, "measured_s": 58})
        self.assertEqual(out["gate"], "PASS")


if __name__ == "__main__":
    unittest.main()
