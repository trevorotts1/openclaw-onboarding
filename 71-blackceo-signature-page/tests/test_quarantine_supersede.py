#!/usr/bin/env python3
"""SWB-210 (1.3.44): the signed quarantine ledger and the stage-scoped supersede rule.

Each check FAILS on 1.3.43 (no quarantine, no supersede) and PASSES on 1.3.44.
Run: python3 tests/test_quarantine_supersede.py
"""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import governed_runner  # noqa: E402
import quarantine_ledger  # noqa: E402

oop = governed_runner.detector()

GATE_PASS = "import sys\nprint('PASS'); sys.exit(0)\n"
KEY = b"operator-test-key-0123456789abcdef"
OTHER_KEY = b"some-other-key-0123456789abcdef!"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.run_root = t / "run"
        self.run_root.mkdir()
        (self.run_root / "intake.json").write_text(
            json.dumps({"page_kind": "sales", "copy_version": "standard"}), encoding="utf-8")
        gate = t / "gate.py"
        gate.write_text(GATE_PASS, encoding="utf-8")
        self._gate = governed_runner.GATE_PATH
        governed_runner.GATE_PATH = gate
        self.addCleanup(setattr, governed_runner, "GATE_PATH", self._gate)
        self.key = self.make_key(KEY, "key")
        old = os.environ.get("SF_PIN_AUTHORITY_KEY_FILE")
        os.environ["SF_PIN_AUTHORITY_KEY_FILE"] = str(self.key)
        self.addCleanup(self.restore_env, old)

    def restore_env(self, old):
        if old is None:
            os.environ.pop("SF_PIN_AUTHORITY_KEY_FILE", None)
        else:
            os.environ["SF_PIN_AUTHORITY_KEY_FILE"] = old

    def make_key(self, data, name):
        path = Path(self.tmp.name) / name
        path.write_bytes(data)
        path.chmod(0o600)
        return path

    def write(self, rel, text="x"):
        path = self.run_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def govern(self, rel, stage, text="v1"):
        self.write(rel, text)
        governed_runner.register_output(self.run_root, rel, stage=stage)
        governed_runner.close_output(self.run_root, rel, stage=stage)

    def dispatch(self, stage="desktop-wireframe", authority="paid_dispatch"):
        return governed_runner.admit(self.run_root, kind="direct_executor",
                                     authority=authority, stage=stage)

    def ledger(self):
        return json.loads((self.run_root / "private" / "quarantine-ledger.json").read_text())

    def save_ledger(self, doc):
        (self.run_root / "private" / "quarantine-ledger.json").write_text(json.dumps(doc))


class TestQuarantine(Base):
    def test_absent_ledger_is_old_behaviour(self):
        self.write("stray.png", "stray")
        result = governed_runner.scan(self.run_root)
        self.assertNotIn("quarantined", result)
        self.assertEqual([e["path"] for e in result["ungoverned"]], ["stray.png"])
        self.assertEqual(result["ungoverned"][0]["reason"], "not registered with the pipeline")
        with self.assertRaises(governed_runner.AdmissionRefused) as ctx:
            self.dispatch()
        self.assertNotIn("quarantined", ctx.exception.decision["out_of_pipeline"])
        self.assertNotIn("quarantined_count", governed_runner.delivery(self.run_root, []))

    def test_signed_entry_acknowledges_and_dispatch_is_admitted(self):
        self.write("stray.png", "stray")
        entry = governed_runner.quarantine(self.run_root, "stray.png", reason="old test image",
                                           approver="Trevor")
        for field in ("path", "sha256", "size", "reason", "quarantined_at", "approver", "signature"):
            self.assertIn(field, entry)
        result = governed_runner.scan(self.run_root)
        self.assertEqual([e["path"] for e in result["quarantined"]], ["stray.png"])
        self.assertEqual(result["ungoverned"], [])
        self.assertTrue(result["ok"])
        decision = self.dispatch()
        self.assertTrue(decision["admitted"])
        self.assertEqual(decision["out_of_pipeline"]["quarantined_count"], 1)
        self.assertEqual(decision["out_of_pipeline"]["quarantined"], ["stray.png"])
        self.assertEqual(governed_runner.delivery(self.run_root, [])["quarantined_count"], 1)

    def test_forged_signature_refuses(self):
        self.write("stray.png", "stray")
        governed_runner.quarantine(self.run_root, "stray.png", reason="r", approver="Trevor")
        doc = self.ledger()
        doc["entries"][0]["signature"] = "0" * 64
        self.save_ledger(doc)
        self.assertEqual(governed_runner.scan(self.run_root)["quarantined"], [])
        with self.assertRaises(governed_runner.AdmissionRefused):
            self.dispatch()

    def test_entry_signed_with_another_key_refuses(self):
        self.write("stray.png", "stray")
        other = self.make_key(OTHER_KEY, "other")
        with self.assertRaises(ValueError):    # 1.3.50: a foreign key cannot even anchor the run
            governed_runner.quarantine(self.run_root, "stray.png", reason="r", approver="Trevor",
                                       key_file=str(other))
        result = governed_runner.scan(self.run_root)
        self.assertEqual(result.get("quarantined", []), [])
        self.assertEqual([e["path"] for e in result["ungoverned"]], ["stray.png"])

    def test_missing_signature_and_edited_fields_refuse(self):
        self.write("stray.png", "stray")
        governed_runner.quarantine(self.run_root, "stray.png", reason="r", approver="Trevor")
        doc = self.ledger()
        edited = json.loads(json.dumps(doc))
        edited["entries"][0]["reason"] = "a different reason"
        self.save_ledger(edited)
        self.assertEqual(governed_runner.scan(self.run_root)["quarantined"], [])
        del doc["entries"][0]["signature"]
        self.save_ledger(doc)
        self.assertEqual(governed_runner.scan(self.run_root)["quarantined"], [])

    def test_changed_file_leaves_entry_useless(self):
        self.write("stray.png", "stray")
        governed_runner.quarantine(self.run_root, "stray.png", reason="r", approver="Trevor")
        self.write("stray.png", "stray but changed")
        result = governed_runner.scan(self.run_root)
        self.assertEqual(result["quarantined"], [])
        self.assertIn("changed after it was quarantined", result["ungoverned"][0]["reason"])
        with self.assertRaises(governed_runner.AdmissionRefused):
            self.dispatch()

    def test_unavailable_key_verifies_nothing(self):
        self.write("stray.png", "stray")
        governed_runner.quarantine(self.run_root, "stray.png", reason="r", approver="Trevor")
        os.environ.pop("SF_PIN_AUTHORITY_KEY_FILE")
        self.assertEqual(governed_runner.scan(self.run_root)["quarantined"], [])

    def test_key_must_be_0600_and_outside_the_run(self):
        self.write("stray.png", "stray")
        loose = self.make_key(KEY, "loose")
        loose.chmod(0o644)
        with self.assertRaises(ValueError):
            governed_runner.quarantine(self.run_root, "stray.png", reason="r", approver="T",
                                       key_file=str(loose))
        inside = self.run_root / "key"
        inside.write_bytes(KEY)
        inside.chmod(0o600)
        with self.assertRaises(ValueError):
            governed_runner.quarantine(self.run_root, "stray.png", reason="r", approver="T",
                                       key_file=str(inside))

    def test_quarantined_path_can_never_be_registered_or_closed(self):
        self.write("final-mockups/img.png", "img")
        governed_runner.quarantine(self.run_root, "final-mockups/img.png", reason="r",
                                   approver="Trevor")
        with self.assertRaises(ValueError):
            governed_runner.register_output(self.run_root, "final-mockups/img.png",
                                            stage="final-mockups")
        with self.assertRaises(ValueError):
            governed_runner.close_output(self.run_root, "final-mockups/img.png",
                                         stage="final-mockups")
        # tampering with the entry must not reopen the door
        doc = self.ledger()
        doc["entries"][0]["signature"] = "bad"
        self.save_ledger(doc)
        with self.assertRaises(ValueError):
            governed_runner.register_output(self.run_root, "final-mockups/img.png",
                                            stage="final-mockups")
        self.assertNotIn("final-mockups/img.png",
                         oop.load(self.run_root)["outputs"])

    def test_generated_image_cannot_be_quarantined_then_laundered_or_hidden(self):
        self.govern("image-generation-qc/a.png", "image-generation-qc")
        with self.assertRaises(ValueError):
            governed_runner.quarantine(self.run_root, "image-generation-qc/a.png",
                                       reason="hide it", approver="Trevor")
        # a registered file that later changes stays a mismatch, never quarantined
        self.write("image-generation-qc/a.png", "edited")
        self.assertEqual(len(governed_runner.scan(self.run_root)["content_mismatch"]), 1)

    def test_quarantined_files_are_excluded_from_delivery(self):
        self.write("stray.png", "stray")
        self.govern("copy/c.md", "copy")
        governed_runner.quarantine(self.run_root, "stray.png", reason="r", approver="Trevor")
        split = governed_runner.delivery(
            self.run_root, [{"path": "stray.png"}, {"path": "copy/c.md"}])
        self.assertEqual([e["path"] for e in split["admitted"]], ["copy/c.md"])
        self.assertEqual([e["path"] for e in split["excluded"]], ["stray.png"])
        self.assertFalse(split["excluded"][0]["verified"])

    def test_registered_path_in_a_hand_written_ledger_still_counts_mismatch(self):
        self.govern("copy/c.md", "copy")
        self.write("copy/c.md", "changed")
        # forge a validly-signed entry by hand for a registered path
        entry = {"path": "copy/c.md", "sha256": oop._sha256_file(self.run_root / "copy/c.md"),
                 "size": 7, "reason": "r", "quarantined_at": "now", "approver": "T"}
        entry["signature"] = oop._entry_signature(entry, KEY)
        self.save_ledger({"entries": [entry]})
        result = governed_runner.scan(self.run_root)
        self.assertEqual([e["path"] for e in result["content_mismatch"]], ["copy/c.md"])
        self.assertEqual(result["quarantined"], [])

    def test_cli_add_and_status(self):
        self.write("stray.png", "stray")
        self.assertEqual(quarantine_ledger.main(
            ["add", "--run", str(self.run_root), "--path", "stray.png",
             "--reason", "r", "--approver", "Trevor"]), 0)
        self.assertEqual(quarantine_ledger.main(["status", "--run", str(self.run_root)]), 0)
        self.assertEqual(quarantine_ledger.main(
            ["add", "--run", str(self.run_root), "--path", "missing.png",
             "--reason", "r", "--approver", "Trevor"]), 1)


class TestSupersede(Base):
    def change(self, rel):
        self.write(rel, "bytes changed after closing")

    def test_downstream_set_follows_depends_on(self):
        ds = governed_runner.downstream_stages("desktop-wireframe")
        self.assertIn("desktop-wireframe", ds)
        self.assertNotIn("copy", ds)
        self.assertNotIn("font-action-plan", ds)
        self.assertNotIn("intake", ds)
        self.assertIn("final-mockups", ds)

    def test_mismatch_on_dispatched_stage_is_admitted_and_named(self):
        self.govern("desktop-wireframe/section-plan.json", "desktop-wireframe", "old")
        old = oop._sha256_file(self.run_root / "desktop-wireframe/section-plan.json")
        self.change("desktop-wireframe/section-plan.json")
        with self.assertRaises(governed_runner.AdmissionRefused):
            self.dispatch(authority="installation")
        decision = self.dispatch()
        self.assertTrue(decision["admitted"])
        row, = decision["out_of_pipeline"]["superseded_mismatch"]
        self.assertEqual(row["path"], "desktop-wireframe/section-plan.json")
        self.assertEqual(row["owner_stage"], "desktop-wireframe")
        self.assertEqual(row["old_sha256"], old)
        self.assertEqual(row["new_sha256"],
                         oop._sha256_file(self.run_root / "desktop-wireframe/section-plan.json"))

    def test_mismatch_on_downstream_stage_is_admitted(self):
        self.govern("mobile-tablet/a.json", "mobile-tablet", "old")
        self.change("mobile-tablet/a.json")
        decision = self.dispatch("desktop-wireframe")
        self.assertEqual(decision["out_of_pipeline"]["superseded_mismatch"][0]["owner_stage"],
                         "mobile-tablet")

    def test_mismatch_on_upstream_stage_still_refuses(self):
        self.govern("copy/public-copy.md", "copy", "old")
        self.change("copy/public-copy.md")
        with self.assertRaises(governed_runner.AdmissionRefused) as ctx:
            self.dispatch("desktop-wireframe")
        self.assertIn("copy/public-copy.md", ctx.exception.decision["reason"])

    def test_one_upstream_among_admissible_still_refuses(self):
        self.govern("desktop-wireframe/a.json", "desktop-wireframe", "old")
        self.govern("copy/public-copy.md", "copy", "old")
        self.change("desktop-wireframe/a.json")
        self.change("copy/public-copy.md")
        with self.assertRaises(governed_runner.AdmissionRefused) as ctx:
            self.dispatch("desktop-wireframe")
        self.assertNotIn("desktop-wireframe/a.json", ctx.exception.decision["reason"])

    def test_dispatch_of_a_later_stage_does_not_supersede_an_earlier_one(self):
        self.govern("desktop-wireframe/a.json", "desktop-wireframe", "old")
        self.change("desktop-wireframe/a.json")
        with self.assertRaises(governed_runner.AdmissionRefused):
            self.dispatch("final-mockups")

    def test_supersede_is_only_for_paid_dispatch(self):
        self.govern("desktop-wireframe/a.json", "desktop-wireframe", "old")
        self.change("desktop-wireframe/a.json")
        for authority in ("installation", "publishing"):
            with self.assertRaises(governed_runner.AdmissionRefused):
                self.dispatch("desktop-wireframe", authority=authority)

    def test_supersede_does_not_admit_ungoverned_files(self):
        self.govern("desktop-wireframe/a.json", "desktop-wireframe", "old")
        self.change("desktop-wireframe/a.json")
        self.write("desktop-wireframe/stray.json", "not registered")
        with self.assertRaises(governed_runner.AdmissionRefused) as ctx:
            self.dispatch()
        self.assertIn("desktop-wireframe/stray.json", ctx.exception.decision["reason"])

    def test_no_mismatch_decision_has_no_supersede_key(self):
        self.govern("copy/c.md", "copy")
        decision = self.dispatch()
        self.assertNotIn("superseded_mismatch", decision["out_of_pipeline"])
        self.assertTrue(decision["out_of_pipeline"]["ok"])


if __name__ == "__main__":
    unittest.main()
