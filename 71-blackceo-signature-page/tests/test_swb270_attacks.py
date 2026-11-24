#!/usr/bin/env python3
"""SWB-270 (1.3.50): anchor at the first signed record, and reanchor never trusts state.json.

THREAT MODEL M: the actor can WRITE ANY FILE inside the run folder (including private/state.json)
but holds no operator key and cannot write the anchor outside the run. Known baseline limitations
(unsigned registry, keyless register_output, symlinked-directory scan skip: N01-N04, N11) are not
tested. Closed here (found by the SWB-260 check on 1.3.49):
  X1d  M sets state.json run_id back to run A before the operator runs reanchor --confirm-recreated-run;
       1.3.49 signed the new generation for run A, never retired run A, and the replayed records passed
  X9   a run that rebinds but never quarantines had NO anchor; after recreation M planted A's
       rebind records and set state.json back to run A
Every ATTACK test passes when the attack is REFUSED; the ones named in FAILS_ON_1349 fail on 1.3.49.
RESIDUAL (documented, not tested as a refusal): same folder kept, contents replaced (X5).
Throwaway keys only. Run: python3 tests/test_swb270_attacks.py
"""
import contextlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import governed_runner as GR  # noqa: E402
import quarantine_ledger  # noqa: E402
from test_quarantine_supersede import KEY  # noqa: E402
from test_runstate_owner_collision import sha  # noqa: E402
from test_swb250_attacks import REL, COPY, COPY2, DW  # noqa: E402
from test_swb260_attacks import Base260, P  # noqa: E402

oop = GR.detector()


class Base270(Base260):
    def reanchor(self, **kw):
        args = dict(confirm_recreated_run=True, reason="recreated", approver="T",
                    new_run_id=json.loads((self.run_root / P / "state.json").read_text())["run_id"])
        args.update(kw)
        return GR.reanchor(self.run_root, **args)

    def anchor_doc(self):
        return json.loads(self.anchor_file().read_text())

    def attack_admitted(self):
        return (self.governed(COPY), self.admitted(), oop._ledger_status(self.run_root)["ok"])


class TestX1dReanchorNeverTrustsState(Base270):
    def scenario(self):
        self.hide()
        self.rebound_copy()
        old = self.snap()
        self.recreate("run-B")
        (self.run_root / REL).unlink()
        return old

    def test_X1d_state_json_set_back_to_run_A_before_reanchor_refuses(self):
        old = self.scenario()
        self.set_run_id("run-A")            # M, before the operator runs reanchor
        self.assertTrue(self.refuses(self.reanchor))
        self.plant({k: v for k, v in old.items() if k not in ("state.json",)})
        self.assertEqual(self.attack_admitted(), (False, False, False))
        self.assertEqual(self.anchor_doc()["generation"], 1)    # nothing was re-signed

    def test_X1d_even_when_the_folder_inode_changed_the_old_id_is_refused(self):
        old = self.scenario()
        self.set_run_id("run-A")
        err = None
        try:
            self.reanchor()
        except ValueError as exc:
            err = str(exc)
        self.assertIsNotNone(err)
        self.assertIn("old anchor's run_id", err)
        self.assertEqual(self.anchor_doc()["run"]["run_id"], "run-A")

    def test_X1c_variant_set_back_without_any_ledger_files(self):
        self.scenario()
        self.set_run_id("run-A")
        self.assertTrue(self.refuses(self.reanchor))

    def test_X1d_command_line_refuses_too(self):
        self.scenario()
        self.set_run_id("run-A")
        rc, out, err = self.cli(["reanchor", "--run", str(self.run_root), "--confirm-recreated-run",
                                 "--new-run-id", "run-A", "--reason", "r", "--approver", "T"])
        self.assertEqual(rc, 1)
        self.assertEqual(self.anchor_doc()["generation"], 1)

    def test_reanchor_with_a_retired_id_refuses(self):
        self.scenario()
        self.set_run_id("run-B")
        self.reanchor()                               # A retired, B anchored
        self.recreate("run-C")
        self.set_run_id("run-A")                      # M: an id retired by the first reanchor
        self.assertTrue(self.refuses(self.reanchor))
        self.assertTrue(self.refuses(self.reanchor, new_run_id="run-A"))
        self.assertTrue(self.refuses(GR.reanchor, self.run_root, confirm_recreated_run=True,
                                     new_run_id="run-B", reason="r", approver="T"))

    def test_reanchor_with_mismatching_new_run_id_refuses(self):
        self.scenario()
        self.set_run_id("run-B")
        self.assertTrue(self.refuses(self.reanchor, new_run_id="run-Z"))
        self.assertTrue(self.refuses(self.reanchor, new_run_id=""))
        self.assertTrue(self.refuses(self.reanchor, new_run_id=None))
        self.assertTrue(self.refuses(GR.reanchor, self.run_root, confirm_recreated_run=True,
                                     reason="r", approver="T"))
        rc, out, err = self.cli(["reanchor", "--run", str(self.run_root), "--confirm-recreated-run",
                                 "--reason", "r", "--approver", "T"])
        self.assertEqual(rc, 1)
        self.assertIn("--new-run-id", err)

    def test_control_a_genuinely_new_run_id_reanchors_and_the_old_records_stay_void(self):
        old = self.scenario()
        self.set_run_id("run-B")
        r = self.reanchor(new_run_id="run-B")
        self.assertEqual((r["old_run_id"], r["new_run_id"], r["generation"]), ("run-A", "run-B", 2))
        self.plant({k: v for k, v in old.items() if k != "state.json"})
        self.assertEqual(self.attack_admitted(), (False, False, False))
        self.set_run_id("run-A")                       # state back to the retired id afterwards
        self.assertEqual(self.attack_admitted(), (False, False, False))
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])


class TestX9NoAnchorRun(Base270):
    def test_X9_a_run_that_only_rebinds_has_an_anchor_and_replay_into_B_refuses(self):
        self.rebound_copy()                            # rebind only: no quarantine
        self.assertTrue(any(self.anchor_dir().glob("*.json")), "no anchor at the first signed record")
        old = self.snap()
        self.recreate("run-B")
        (self.run_root / REL).unlink() if (self.run_root / REL).exists() else None
        self.plant({k: v for k, v in old.items() if k != "state.json"})
        self.set_run_id("run-A")
        self.assertFalse(self.governed(COPY), "rebind of run A revived in recreated folder")
        self.assertFalse(self.admitted())

    def test_X9_no_anchor_at_all_and_planted_rebind_records_refuse_until_adopt(self):
        self.rebound_copy()
        old = self.snap()
        shutil.rmtree(self.anchor_dir())               # a pre-1.3.50 run: signed records, no anchor
        self.recreate("run-B")
        self.plant({k: v for k, v in old.items() if k != "state.json"})
        self.set_run_id("run-A")
        self.assertFalse(self.governed(COPY))
        self.assertFalse(self.admitted())
        self.assertFalse(self.anchor_dir().exists(), "a verifier created the anchor")


class TestUnanchoredRunWithSignedRecords(Base270):
    def planted_run(self):
        self.rebound_copy()
        GR.reown(self.run_root, COPY, owner_stage="copy", reason="r", approver="T")
        shutil.rmtree(self.anchor_dir())

    def test_every_verifier_refuses_and_none_creates_an_anchor(self):
        self.planted_run()
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertIn("adopt-unanchored", oop._ledger_status(self.run_root)["why"])
        self.assertFalse(self.governed(COPY))
        self.assertFalse(self.admitted())
        self.assertEqual(oop.run_identity(self.run_root)["run_id"], oop.REFUSED_RUN_ID)
        GR.scan(self.run_root)
        GR.delivery(self.run_root, [{"path": COPY}])
        self.cli(["status", "--run", str(self.run_root)])
        self.assertFalse(self.anchor_dir().exists())

    def test_every_signing_writer_refuses_too(self):
        self.planted_run()
        self.write("stray.png", "s")
        self.assertTrue(self.refuses(GR.quarantine, self.run_root, "stray.png", reason="r", approver="T"))
        self.assertTrue(self.refuses(GR.rebind, self.run_root, COPY, stage="copy", reason="r", approver="T"))
        self.assertTrue(self.refuses(GR.reown, self.run_root, COPY, owner_stage="copy", reason="r", approver="T"))
        self.assertFalse(self.admitted())
        self.assertFalse(self.anchor_dir().exists())

    def test_the_operator_adopts_it_after_a_listing_and_needs_yes_non_interactively(self):
        self.planted_run()
        rc, out, err = self.cli(["adopt-unanchored", "--run", str(self.run_root)])
        self.assertEqual(rc, 1)
        self.assertIn(COPY, out)
        self.assertIn("rebind", out)
        self.assertIn("reown", out)
        self.assertIn("bound here", out)
        self.assertIn("--yes", err)
        self.assertFalse(self.anchor_dir().exists())
        rc, out, err = self.cli(["adopt-unanchored", "--run", str(self.run_root), "--yes"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.anchor_doc()["run"]["run_id"], "run-A")
        self.assertTrue(self.governed(COPY))

    def test_adopt_lists_records_of_another_run_as_void(self):
        self.planted_run()
        self.set_run_id("run-Z")
        plan = GR.adopt_unanchored(self.run_root, dry_run=True)
        self.assertIn("VOID (named for", plan["listing"])
        self.assertFalse(self.anchor_dir().exists())

    def test_adopt_refuses_when_an_anchor_exists(self):
        self.rebound_copy()
        self.assertTrue(self.refuses(GR.adopt_unanchored, self.run_root))

    def test_junk_and_foreign_key_rows_do_not_count_as_signed_records(self):
        (self.run_root / P / "rebind-records.json").write_text(json.dumps(
            {"entries": [{"path": COPY, "signature": "00" * 32}]}))
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])
        self.write("stray.png", "s")
        GR.quarantine(self.run_root, "stray.png", reason="r", approver="T")    # the first genuine record anchors


class TestAnchorAtFirstSignedRecord(Base270):
    """Every operator-signed writer creates the anchor (run_id from state.json, generation 1)
    before or with its first record, in a fresh run."""

    def check_anchor(self):
        docs = list(self.anchor_dir().glob("*.json"))
        self.assertEqual(len(docs), 1)
        doc = json.loads(docs[0].read_text())
        self.assertEqual((doc["run"]["run_id"], doc["generation"]), ("run-A", 1))
        self.assertTrue(oop._anchor_verdict(self.run_root, KEY if isinstance(KEY, bytes) else KEY.encode())["ok"])

    def test_control_nothing_signed_nothing_anchored(self):
        self.govern(COPY, "copy", "v1")
        GR.scan(self.run_root)
        self.assertFalse(self.anchor_dir().exists())

    def test_add(self):
        self.write("stray.png", "s")
        GR.quarantine(self.run_root, "stray.png", reason="r", approver="T")
        self.check_anchor()

    def test_rebind(self):
        self.rebound_copy()
        self.check_anchor()

    def test_reown(self):
        self.govern(COPY, "copy", "v1")
        GR.reown(self.run_root, COPY, owner_stage="copy", reason="r", approver="T")
        self.check_anchor()

    def test_acknowledge_input(self):
        self.govern(COPY2, "copy", "old")
        self.write(COPY2, "new")
        GR.acknowledge_input(self.run_root, COPY2, old_sha256=sha("old"), new_sha256=sha("new"),
                             reason="r", approver="T")
        self.check_anchor()

    def test_the_governors_admission_row(self):
        self.govern(COPY, "copy", "v1")
        self.admitted("copy")
        self.check_anchor()

    def test_the_anchor_exists_before_the_record_is_visible(self):
        """run_identity(strict=True) is the call every writer makes first: it anchors then returns."""
        self.assertFalse(self.anchor_dir().exists())
        ident = oop.run_identity(self.run_root, strict=True, key=KEY if isinstance(KEY, bytes) else KEY.encode())
        self.assertEqual(ident["run_id"], "run-A")
        self.check_anchor()

    def test_verifiers_never_create_one(self):
        self.govern(COPY, "copy", "v1")
        GR.scan(self.run_root)
        oop._ledger_status(self.run_root)
        oop.run_identity(self.run_root)
        oop.verify_admission({"signature": "x"}, KEY, root=self.run_root)
        GR.delivery(self.run_root, [{"path": COPY}])
        self.cli(["status", "--run", str(self.run_root)])
        self.assertFalse(self.anchor_dir().exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
