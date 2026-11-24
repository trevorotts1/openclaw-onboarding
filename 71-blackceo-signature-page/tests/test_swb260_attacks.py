#!/usr/bin/env python3
"""SWB-260 (1.3.49): the operator anchor holds the run identity, under THREAT MODEL M.

M: the actor can WRITE ANY FILE inside the run folder (including private/state.json) but holds no
operator key and cannot write the anchor outside the run. Known baseline limitations (unsigned
registry, keyless register_output, symlinked-directory scan skip: N01-N04, N11) are not tested.

Covered: R2 (run recreated at the same root, genuinely signed records of run A planted, state.json
rewritten back to run A) and its variants; a leftover anchor refuses a new run until the operator
runs `reanchor`; `reanchor` is never implicit, needs the flag, reason, approver and the key; a
restored older anchor cannot revive a retired run; verifiers never create or replace an anchor;
`seal --adopt-legacy` prints every path and sha256 and refuses non-interactively without --yes.
Every ATTACK test passes when the attack is REFUSED. Throwaway keys only.
Run: python3 tests/test_swb260_attacks.py
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
from test_quarantine_supersede import KEY, OTHER_KEY  # noqa: E402
from test_runstate_owner_collision import sha  # noqa: E402
from test_swb250_attacks import Base250, REL, COPY, DW, IMG  # noqa: E402

oop = GR.detector()
P = "private/"
FILES = ["quarantine-ledger.json", "quarantine-seal.json", "quarantine-releases.json",
         "reown-records.json", "rebind-records.json", "input-acknowledgements.json",
         "governed-outputs.json", "state.json"]


class Base260(Base250):
    def setUp(self):
        super().setUp()
        self.set_run_id("run-A")

    def snap(self):
        return {f: (self.run_root / P / f).read_bytes() for f in FILES
                if (self.run_root / P / f).exists()}

    def plant(self, snap, skip=("state.json",)):
        for f, b in snap.items():
            if f not in skip:
                (self.run_root / P / f).parent.mkdir(parents=True, exist_ok=True)
                (self.run_root / P / f).write_bytes(b)

    def rebound_copy(self):
        self.govern(COPY, "copy", "v1")
        self.write(COPY, "v2")
        GR.rebind(self.run_root, COPY, stage="copy", reason="owner edit", approver="T")

    def recreate(self, run_id, files=True):
        """The operator (or M) deletes the run folder and makes a new run at the same path."""
        shutil.rmtree(self.run_root)
        self.run_root.mkdir()
        (self.run_root / "intake.json").write_text(json.dumps(
            {"page_kind": "sales", "copy_version": "standard"}))
        self.set_run_id(run_id)
        if files:
            self.write(COPY, "v2")
            (self.run_root / REL).parent.mkdir(parents=True, exist_ok=True)
            (self.run_root / REL).write_bytes(IMG)

    def anchor_file(self):
        return next(f for f in self.anchor_dir().glob("*.json") if ".retired" not in f.name)

    def anchor_state(self):
        d = self.anchor_dir()
        return {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in d.glob("*")} if d.exists() else None

    def reanchor(self, **kw):
        args = dict(confirm_recreated_run=True, reason="recreated", approver="T")
        args.update(kw)
        return GR.reanchor(self.run_root, **args)

    def cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = quarantine_ledger.main(argv)
        return rc, out.getvalue(), err.getvalue()


class TestR2(Base260):
    def scenario(self, *, reanchor):
        self.hide()
        self.rebound_copy()
        self.write(REL, "regen")
        GR.release_quarantine(self.run_root, REL, stage=DW, reason="r", approver="T")
        old = self.snap()
        self.recreate("run-B")
        if reanchor:
            self.reanchor()
        self.plant(old)
        return old

    def attack_outcome(self):
        return (self.governed(COPY), self.admitted(), oop._ledger_status(self.run_root)["ok"])

    def test_R2_original_leftover_anchor_state_json_rewritten_to_run_A(self):
        self.scenario(reanchor=False)
        self.set_run_id("run-A")
        self.assertFalse(self.attack_outcome()[1], "run A's records revived in recreated run B")
        self.assertFalse(self.governed(COPY))

    def test_R2_after_the_operator_reanchors_run_B_state_json_rewritten_to_run_A(self):
        self.scenario(reanchor=True)
        self.assertEqual(self.attack_outcome()[:2], (False, False))   # run-B id, planted records
        self.set_run_id("run-A")
        self.assertEqual(self.attack_outcome(), (False, False, False))
        self.assertIn("anchor", oop._ledger_status(self.run_root)["why"])

    def test_R2_reanchored_run_B_with_a_restored_run_A_anchor_is_refused(self):
        """Rollback of the anchor generation: the older signed anchor put back (it is outside M)."""
        self.scenario(reanchor=False)
        older = self.anchor_file().read_bytes()
        self.reanchor()
        self.assertEqual(json.loads(self.anchor_file().read_text())["generation"], 2)
        self.anchor_file().write_bytes(older)           # roll the anchor back to generation 1
        self.set_run_id("run-A")
        self.assertFalse(self.attack_outcome()[1])

    def test_R2_rolled_back_anchor_with_state_json_still_run_B_is_refused(self):
        self.scenario(reanchor=False)
        older = self.anchor_file().read_bytes()
        self.reanchor()
        self.anchor_file().write_bytes(older)
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertFalse(self.admitted())

    def test_R2_state_json_rewritten_with_the_anchors_run_id_but_a_recreated_folder(self):
        """No reanchor, folder deleted and made again: the anchor still names run A's folder."""
        self.hide()
        self.recreate("run-A")
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertIn("folder", oop._ledger_status(self.run_root)["why"])

    def test_the_anchor_run_id_is_the_authority_over_state_json(self):
        self.hide()
        self.assertEqual(json.loads(self.anchor_file().read_text())["run"]["run_id"], "run-A")
        self.set_run_id("run-X")
        self.assertEqual(oop.run_identity(self.run_root)["run_id"], oop.REFUSED_RUN_ID)
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertFalse(self.admitted())
        self.set_run_id("run-A")                          # the legitimate id is honoured again
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])

    def test_signing_refuses_while_the_anchor_refuses_the_run(self):
        self.hide()
        self.set_run_id("run-X")
        self.write("stray.png", "s")
        self.assertTrue(self.refuses(GR.quarantine, self.run_root, "stray.png", reason="r",
                                     approver="T"))
        self.assertTrue(self.refuses(GR.rebind, self.run_root, COPY, stage="copy", reason="r",
                                     approver="T"))
        decision = {"x": 1}
        self.assertFalse(oop.sign_admission(self.run_root, decision))

    def test_control_the_legitimate_run_is_unaffected(self):
        self.hide()
        self.rebound_copy()
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])
        self.assertTrue(self.governed(COPY))
        self.write("another.png", "a")
        GR.quarantine(self.run_root, "another.png", reason="r", approver="T")   # re-seals, same run
        self.assertEqual(json.loads(self.anchor_file().read_text())["run"]["run_id"], "run-A")
        self.assertEqual(json.loads(self.anchor_file().read_text())["generation"], 1)


class TestAnchorIsSigned(Base260):
    def test_an_edited_anchor_does_not_verify(self):
        self.hide()
        doc = json.loads(self.anchor_file().read_text())
        doc["run"]["run_id"] = "run-Z"
        self.anchor_file().write_text(json.dumps(doc))
        self.set_run_id("run-Z")
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])

    def test_an_unsigned_1_3_48_anchor_refuses_until_reanchor(self):
        self.hide()
        doc = json.loads(self.anchor_file().read_text())
        self.anchor_file().write_text(json.dumps({"serial": doc["serial"],
                                                  "seal_signature": doc["seal_signature"]}))
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertTrue(self.refuses(GR.quarantine, self.run_root, REL, reason="r", approver="T"))
        self.reanchor()
        self.assertEqual(json.loads(self.anchor_file().read_text())["generation"], 1)   # 0 + 1
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])

    def test_an_anchor_signed_with_another_key_does_not_verify(self):
        self.hide()
        # the same anchor file read with the other key: not valid
        verdict = oop._anchor_verdict(self.run_root, OTHER_KEY.encode()
                                      if isinstance(OTHER_KEY, str) else OTHER_KEY)
        self.assertFalse(verdict["ok"])


class TestVerifiersNeverTouchTheAnchor(Base260):
    def exercise(self):
        GR.scan(self.run_root)
        oop._ledger_status(self.run_root)
        self.admitted("copy")
        GR.delivery(self.run_root, [{"path": COPY}])
        self.cli(["status", "--run", str(self.run_root)])
        oop.run_identity(self.run_root)
        oop.verify_admission({"signature": "x"}, KEY, root=self.run_root)

    def test_no_anchor_means_none_created(self):
        self.govern(COPY, "copy", "v1")
        self.exercise()
        self.assertFalse(self.anchor_dir().exists())

    def test_an_existing_anchor_is_left_byte_for_byte(self):
        self.hide()
        before = self.anchor_state()
        self.exercise()
        self.assertEqual(self.anchor_state(), before)

    def test_a_refused_run_leaves_the_leftover_anchor_alone_and_creates_nothing(self):
        self.hide()
        self.recreate("run-B")
        before = self.anchor_state()
        self.exercise()
        self.assertFalse(self.admitted())
        self.assertEqual(self.anchor_state(), before)

    def test_a_leftover_anchor_refuses_every_new_run_until_reanchor(self):
        self.hide()
        self.recreate("run-B")
        status = oop._ledger_status(self.run_root)
        self.assertFalse(status["ok"])
        self.assertIn("reanchor", status["why"])
        self.assertFalse(self.admitted("copy"))
        self.assertTrue(self.refuses(GR.quarantine, self.run_root, REL, reason="r", approver="T"))
        self.assertTrue(self.refuses(GR.seal_ledger, self.run_root))
        self.assertEqual(self.anchor_state() is not None, True)

    def test_after_reanchor_the_new_run_works_and_a_fresh_ledger_is_possible(self):
        self.hide()
        self.recreate("run-B", files=False)
        r = self.reanchor()
        self.assertEqual((r["old_run_id"], r["new_run_id"], r["generation"]), ("run-A", "run-B", 2))
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])      # nothing sealed yet
        self.assertTrue(self.admitted("copy"))
        self.write("fresh.png", "f")
        GR.quarantine(self.run_root, "fresh.png", reason="r", approver="T")
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])
        doc = json.loads(self.anchor_file().read_text())
        self.assertEqual((doc["run"]["run_id"], doc["generation"]), ("run-B", 2))
        self.assertGreater(doc["serial"], 1)
        self.assertEqual(doc["reanchor"]["old_run_id"], "run-A")


class TestReanchorIsNeverImplicit(Base260):
    def test_without_the_confirm_flag_refuses_and_names_old_and_new(self):
        self.hide()
        self.recreate("run-B")
        before = self.anchor_state()
        with self.assertRaises(ValueError) as ctx:
            self.reanchor(confirm_recreated_run=False)
        text = str(ctx.exception)
        self.assertIn("run-A", text)
        self.assertIn("run-B", text)
        self.assertIn("serial", text)
        self.assertEqual(self.anchor_state(), before)

    def test_command_line_without_the_flag_refuses(self):
        self.hide()
        self.recreate("run-B")
        before = self.anchor_state()
        rc, out, err = self.cli(["reanchor", "--run", str(self.run_root), "--reason", "r",
                                 "--approver", "T"])
        self.assertEqual(rc, 1)
        self.assertIn("refused", err)
        self.assertEqual(self.anchor_state(), before)
        self.assertFalse(self.admitted("copy"))

    def test_command_line_with_the_flag_prints_old_and_new_and_works(self):
        self.hide()
        self.recreate("run-B", files=False)
        rc, out, err = self.cli(["reanchor", "--run", str(self.run_root), "--confirm-recreated-run",
                                 "--reason", "recreated", "--approver", "T"])
        self.assertEqual(rc, 0, err)
        for needle in ("run-A", "run-B", "serial", "generation 2"):
            self.assertIn(needle, out)
        self.assertTrue(self.admitted("copy"))

    def test_needs_a_reason_and_an_approver(self):
        self.hide()
        self.recreate("run-B")
        self.assertTrue(self.refuses(self.reanchor, reason=""))
        self.assertTrue(self.refuses(self.reanchor, approver=" "))

    def test_reanchor_with_a_foreign_key_refuses(self):
        self.hide()
        self.recreate("run-B")
        before = self.anchor_state()
        self.assertTrue(self.refuses(self.reanchor, key_file=self.make_key(OTHER_KEY, "other")))
        self.assertEqual(self.anchor_state(), before)
        self.assertFalse(self.admitted("copy"))

    def test_reanchor_without_any_key_refuses(self):
        self.hide()
        self.recreate("run-B")
        self.assertTrue(self.refuses(self.reanchor, key_file=str(Path(self.tmp.name) / "no-key")))

    def test_reanchor_cannot_replace_an_anchor_that_already_matches(self):
        self.hide()
        before = self.anchor_state()
        self.assertTrue(self.refuses(self.reanchor))
        self.assertEqual(self.anchor_state(), before)

    def test_reanchor_cannot_replace_an_anchor_that_does_not_verify(self):
        self.hide()
        self.anchor_file().write_text("garbage")
        self.assertTrue(self.refuses(self.reanchor))

    def test_reanchor_cannot_reuse_a_retired_run_id(self):
        self.hide()
        self.recreate("run-B")
        self.reanchor()
        self.recreate("run-A")                          # M or the operator brings run A's id back
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertTrue(self.refuses(self.reanchor))

    def test_the_retired_list_is_signed(self):
        self.hide()
        self.recreate("run-B")
        self.reanchor()
        retired = next(self.anchor_dir().glob("*.retired.json"))
        doc = json.loads(retired.read_text())
        doc["retired"] = []
        retired.write_text(json.dumps(doc))
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])

    def test_nothing_in_the_run_folder_is_moved_or_edited_by_reanchor(self):
        self.hide()
        self.recreate("run-B")
        tree = sorted((p.relative_to(self.run_root).as_posix(), p.read_bytes())
                      for p in self.run_root.rglob("*") if p.is_file())
        self.reanchor()
        after = sorted((p.relative_to(self.run_root).as_posix(), p.read_bytes())
                       for p in self.run_root.rglob("*") if p.is_file())
        self.assertEqual(tree, after)


class TestAdoptLegacyPrints(Base260):
    def legacy(self):
        self.write("stray.png", "legacy bytes")
        GR.quarantine(self.run_root, "stray.png", reason="r", approver="T")
        led = json.loads((self.run_root / oop.LEDGER_FILE).read_text())
        for e in led["entries"]:
            e.pop("run")
            e["signature"] = oop._legacy_entry_signature(e, KEY.encode() if isinstance(KEY, str) else KEY)
        (self.run_root / oop.LEDGER_FILE).write_text(json.dumps(led))
        (self.run_root / oop.SEAL_FILE).unlink()
        shutil.rmtree(self.anchor_dir())
        return led["entries"][0]

    def test_non_interactive_without_yes_prints_the_list_and_signs_nothing(self):
        entry = self.legacy()
        before = (self.run_root / oop.LEDGER_FILE).read_bytes()
        rc, out, err = self.cli(["seal", "--run", str(self.run_root), "--adopt-legacy"])
        self.assertEqual(rc, 1)
        self.assertIn("stray.png", out)
        self.assertIn(entry["sha256"], out)
        self.assertIn("--yes", err)
        self.assertEqual((self.run_root / oop.LEDGER_FILE).read_bytes(), before)
        self.assertFalse((self.run_root / oop.SEAL_FILE).exists())

    def test_with_yes_prints_each_path_and_sha_it_re_signs(self):
        entry = self.legacy()
        rc, out, err = self.cli(["seal", "--run", str(self.run_root), "--adopt-legacy", "--yes"])
        self.assertEqual(rc, 0, err)
        self.assertIn("re-signing stray.png sha256=%s" % entry["sha256"], out)
        self.assertIn("re-signed stray.png sha256=%s" % entry["sha256"], out)
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])

    def test_the_library_dry_run_writes_nothing(self):
        self.legacy()
        before = (self.run_root / oop.LEDGER_FILE).read_bytes()
        plan = GR.seal_ledger(self.run_root, adopt_legacy=True, dry_run=True)
        self.assertEqual([r["path"] for r in plan["adopted_entries"]], ["stray.png"])
        self.assertEqual((self.run_root / oop.LEDGER_FILE).read_bytes(), before)
        self.assertFalse(self.anchor_dir().exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
