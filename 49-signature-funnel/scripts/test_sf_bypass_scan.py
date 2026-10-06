#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sf_bypass_scan.py - the entry shell's bypass scan and its Skill 74 allow-list.

Owner order: Skill 74 is the ONE approved KIE path. This proves, through the real entry shell
(`--scan-only`), that (a) a hand-rolled createTask is still refused, and (b) Skill 74's own result
files, recorded through kie74_receipt.py, are not mistaken for one. Exit 0 = all cases hold.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ENTRY = SKILL / "signature-funnel-entry.sh"
RECEIPT = HERE / "kie74_receipt.py"
PY = sys.executable
CREATETASK = "/api/v1/jobs/" + "createTask"


def adapter_result(**over):
    r = {"provider": "kie", "adapter": "74-kie-live-adapter", "adapter_mode": "active",
         "backend": "native-live", "model_id": "model-from-skill-66", "task_id": "task-xyz-001",
         "state": "success", "saved_paths": ["/run/images/a.png"], "fallback_used": False,
         "warnings": [], "data": {"path": CREATETASK}}
    r.update(over)
    return r


def scan(rd):
    return subprocess.run(["bash", str(ENTRY), "--scan-only", "--run-dir", str(rd)],
                          text=True, capture_output=True)


class BypassScan(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.rd = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_clean_run_dir_passes(self):
        (self.rd / "brief.json").write_text("{}", encoding="utf-8")
        self.assertEqual(scan(self.rd).returncode, 0)

    def test_hand_rolled_curl_is_refused(self):
        (self.rd / "driver.sh").write_text("curl -X POST https://api.kie.ai" + CREATETASK + "\n", encoding="utf-8")
        p = scan(self.rd)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("BYPASS-SCAN", p.stderr)

    def test_hand_rolled_python_without_host_is_refused(self):
        (self.rd / "d.py").write_text("BASE = get_base()\nrequests.post(BASE + '" + CREATETASK + "')\n", encoding="utf-8")
        self.assertNotEqual(scan(self.rd).returncode, 0)

    def test_copied_kie_client_script_is_refused(self):
        (self.rd / "run.sh").write_text("python3 kie_image.py --prompt p\n", encoding="utf-8")
        self.assertNotEqual(scan(self.rd).returncode, 0)

    def test_skill74_result_recorded_through_receipt_writer_passes(self):
        res = self.rd / "result.json"
        res.write_text(json.dumps(adapter_result(), indent=2), encoding="utf-8")
        w = subprocess.run([PY, str(RECEIPT), "--run-dir", str(self.rd), "--phase", "P3-IMAGES",
                            "--result", str(res)], text=True, capture_output=True)
        self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
        res.unlink()  # the loose copy is outside the allow-list; the recorded copy is inside it
        stored = self.rd / "receipts" / "kie74" / "task-xyz-001.json"
        self.assertTrue(stored.is_file())
        self.assertIn("createTask", stored.read_text(encoding="utf-8"))
        p = scan(self.rd)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_same_result_outside_the_allow_listed_folder_is_refused(self):
        (self.rd / "result.json").write_text(json.dumps(adapter_result(), indent=2), encoding="utf-8")
        self.assertNotEqual(scan(self.rd).returncode, 0)

    def test_forged_file_inside_the_allow_listed_folder_is_refused(self):
        d = self.rd / "receipts" / "kie74"
        d.mkdir(parents=True)
        (d / "forged.json").write_text('{"cmd": "curl https://api.kie.ai' + CREATETASK + '"}', encoding="utf-8")
        self.assertNotEqual(scan(self.rd).returncode, 0)

    def test_adapter_result_with_a_leaked_token_is_refused(self):
        d = self.rd / "receipts" / "kie74"
        d.mkdir(parents=True)
        leaked = adapter_result(warnings=["Authorization: Bearer abcdefghijklmnop"])
        (d / "leak.json").write_text(json.dumps(leaked, indent=2), encoding="utf-8")
        self.assertNotEqual(scan(self.rd).returncode, 0)

    def test_nested_folder_is_not_allow_listed(self):
        d = self.rd / "receipts" / "kie74" / "sub"
        d.mkdir(parents=True)
        (d / "x.json").write_text(json.dumps(adapter_result(), indent=2), encoding="utf-8")
        self.assertNotEqual(scan(self.rd).returncode, 0)

    def _plant(self, obj):
        d = self.rd / "receipts" / "kie74"
        d.mkdir(parents=True, exist_ok=True)
        (d / "x.json").write_text(json.dumps(obj, indent=2), encoding="utf-8")

    def test_adapter_shape_plus_smuggled_keys_is_refused(self):
        self._plant(adapter_result(cmd="curl https://api.kie.ai" + CREATETASK, x="kie_generate.py"))
        self.assertNotEqual(scan(self.rd).returncode, 0)

    def test_adapter_file_without_a_real_task_id_or_state_is_refused(self):
        self._plant(adapter_result(task_id="placeholder"))
        self.assertNotEqual(scan(self.rd).returncode, 0)
        bad = adapter_result(state="bogus")
        self._plant(bad)
        self.assertNotEqual(scan(self.rd).returncode, 0)

    def test_version_check_is_anchored(self):
        import shutil
        for text, ok in (("v2.1.0", True), ("2.1.0", True), ("v2.0.1-junk", False), ("2.x", False),
                         ("v2.", False), ("v20.0.0", False), ("v2.junk", False), ("v1.9.0", False)):
            with tempfile.TemporaryDirectory() as td:
                shutil.copy(ENTRY, td)
                (Path(td) / "skill-version.txt").write_text(text + "\n", encoding="utf-8")
                (Path(td) / "SKILL.md").write_text("---\nversion: " + text + "\n---\n", encoding="utf-8")  # lockstep gate reads it
                p = subprocess.run(["bash", str(Path(td) / ENTRY.name), "--version-only"],
                                   text=True, capture_output=True)
                self.assertEqual(p.returncode == 0, ok, f"{text!r}: {p.stdout}{p.stderr}")

    def test_shadow_result_is_not_recorded(self):
        res = self.rd / "result.json"
        res.write_text(json.dumps(adapter_result(adapter_mode="shadow", state="skipped", fallback_used=True)),
                       encoding="utf-8")
        w = subprocess.run([PY, str(RECEIPT), "--run-dir", str(self.rd), "--phase", "P3-IMAGES",
                            "--result", str(res)], text=True, capture_output=True)
        self.assertEqual(w.returncode, 2)
        self.assertFalse((self.rd / "delegation_receipts.jsonl").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
