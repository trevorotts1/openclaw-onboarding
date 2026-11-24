#!/usr/bin/env python3
"""SWB-220 (1.3.45) hardened by SWB-230 (1.3.46) and SWB-240 (1.3.47): closed run-state list,
receipt-listed-path owner derivation, signed release-quarantine and reown records, signed
input acknowledgement. Threat model M: the actor writes any run file but lacks the operator key.

Each rule has a negative twin. Attack cases live in tests/test_swb230_attacks.py and
tests/test_swb240_attacks.py.
Run: python3 tests/test_runstate_owner_collision.py
"""
import hashlib
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import governed_runner  # noqa: E402
from test_quarantine_supersede import OTHER_KEY, Base  # noqa: E402

oop = governed_runner.detector()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


REQ = json.dumps({"model": "m", "sections": [1]})
LEDGER = json.dumps({"calls": []})
RESULT = json.dumps({"request_id": "r", "status": "authored", "artifacts": []})


class Helpers(Base):
    def receipt(self, stage, files, status="pass"):
        path = self.run_root / "private" / "receipts" / ("%s.json" % stage)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"stage": stage, "status": status,
                                    "artifact_hashes": {k: sha(v) for k, v in files.items()}}),
                        encoding="utf-8")

    def render(self, rel, text, stage, *, when=None, record_hash=None):
        """What the stage executor does: write the file and list it in
        <stage>/stage-executor-record.json (file + output sha256 + generated_at)."""
        when = when or datetime.now(timezone.utc) + timedelta(seconds=30)
        path = self.write(rel, text)
        rec = self.run_root / stage / "stage-executor-record.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(rec.read_text()) if rec.is_file() else {"stage": stage, "images": []}
        data["generated_at"] = when.isoformat()
        data["images"] = [e for e in data["images"] if e.get("file") != rel] + [
            {"file": rel, "sha256": record_hash or sha(text)}]
        rec.write_text(json.dumps(data), encoding="utf-8")
        stamp = when.timestamp()
        os.utime(rec, (stamp, stamp))
        return path

    def refused_reason(self, stage="desktop-wireframe"):
        with self.assertRaises(governed_runner.AdmissionRefused) as ctx:
            self.dispatch(stage)
        return ctx.exception.decision["reason"]


class TestRunState(Helpers):
    def test_list_is_closed_and_exact(self):
        self.assertEqual(sorted(oop.RUN_STATE_FILES),
                         ["image-spend-ledger.json", "page-result.json", "production-request.json"])

    def test_changed_run_state_is_recorded_and_never_refuses(self):
        for name, old, new in (
                ("production-request.json", REQ, json.dumps({"model": "m2", "sections": [1, 2]})),
                ("image-spend-ledger.json", LEDGER, json.dumps({"calls": [{"n": 1}]})),
                ("page-result.json", RESULT,
                 json.dumps({"request_id": "r", "status": "x", "artifacts": [1]}))):
            self.govern(name, "intake", old)
            self.write(name, new)
        decision = self.dispatch()
        rows = {r["path"]: r for r in decision["out_of_pipeline"]["run_state_changed"]}
        self.assertEqual(sorted(rows), sorted(oop.RUN_STATE_FILES))
        self.assertEqual(rows["production-request.json"]["old_sha256"], sha(REQ))
        self.assertEqual(rows["production-request.json"]["new_sha256"],
                         sha(json.dumps({"model": "m2", "sections": [1, 2]})))
        self.assertTrue(decision["out_of_pipeline"]["ok"])
        self.assertEqual(decision["out_of_pipeline"]["content_mismatch"], [])
        for stage in ("copy", "final-mockups", "responsive-html"):
            self.assertTrue(self.dispatch(stage)["admitted"])

    def test_run_state_is_not_delivered(self):
        self.govern("production-request.json", "intake", REQ)
        self.write("production-request.json", json.dumps({"model": "z", "sections": []}))
        split = governed_runner.delivery(self.run_root, [{"path": "production-request.json"}])
        self.assertEqual([e["path"] for e in split["excluded"]], ["production-request.json"])

    def test_name_in_a_subfolder_refuses(self):
        self.govern("desktop-wireframe/production-request.json", "copy", REQ)
        self.write("desktop-wireframe/production-request.json", json.dumps({"model": "q", "sections": []}))
        self.assertIn("desktop-wireframe/production-request.json", self.refused_reason())

    def test_a_name_outside_the_list_refuses(self):
        for name in ("production-request-desktop-wireframe.json", "production-request.json.bak",
                     "Production-Request.json", "request.json", "page-result.json.old"):
            self.govern(name, "copy", REQ)
            self.write(name, json.dumps({"model": "q", "sections": []}))
        reason = self.refused_reason()
        for name in ("production-request-desktop-wireframe.json", "production-request.json.bak",
                     "Production-Request.json", "request.json", "page-result.json.old"):
            self.assertIn(name, reason)

    def test_unregistered_run_state_name_stays_ungoverned(self):
        self.write("production-request.json", REQ)
        self.assertIn("production-request.json", self.refused_reason())

    def test_in_progress_registration_is_not_run_state(self):
        self.write("page-result.json", RESULT)
        governed_runner.register_output(self.run_root, "page-result.json", stage="intake")
        result = governed_runner.scan(self.run_root)
        self.assertEqual(result["run_state_changed"], [])
        self.assertEqual([e["path"] for e in result["registered_unfinished"]], ["page-result.json"])

    def test_wrong_shape_or_bytes_cannot_ride_on_a_run_state_name(self):
        cases = {"image-spend-ledger.json": ["\x89PNG not json at all", json.dumps([1, 2]),
                                             json.dumps({"calls": "no"}), json.dumps({"other": 1})],
                 "production-request.json": [json.dumps({"model": "m"}), "plain text"],
                 "page-result.json": [json.dumps({"status": "x"})]}
        for name, bad in cases.items():
            for index, text in enumerate(bad):
                self.govern(name, "intake", REQ if name == "production-request.json" else
                            (LEDGER if "ledger" in name else RESULT))
                self.write(name, text)
                self.assertEqual(len(governed_runner.scan(self.run_root)["content_mismatch"]), 1,
                                 (name, index))
                self.assertIn(name, self.refused_reason())
                (self.run_root / name).unlink()
                reg = oop.load(self.run_root)
                reg["outputs"].pop(name)
                oop.save(self.run_root, reg)

    def test_generated_image_named_as_run_state_refuses(self):
        self.govern("image-spend-ledger.json", "intake", LEDGER)
        (self.run_root / "image-spend-ledger.json").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00binary")
        self.assertIn("image-spend-ledger.json", self.refused_reason())


class TestBrandInput(Helpers):
    BRAND = json.dumps({"brand_id": "b", "palette": {}})

    def setUp(self):
        super().setUp()
        (self.run_root / "intake.json").write_text(
            json.dumps({"page_kind": "sales", "copy_version": "standard",
                        "brand_file": "Dr. Brand"}), encoding="utf-8")
        (self.run_root / "launch.json").write_text(
            json.dumps({"brand_hash": sha(self.BRAND)}), encoding="utf-8")

    def edited(self):
        self.govern("Dr. Brand", "intake", self.BRAND)
        new = json.dumps({"brand_id": "b", "palette": {"x": 1}})
        self.write("Dr. Brand", new)
        return new

    def ack(self, new, old=None, key_file=None):
        return governed_runner.acknowledge_input(
            self.run_root, "Dr. Brand", old_sha256=old or sha(self.BRAND), new_sha256=sha(new),
            reason="owner edited the brand profile", approver="Trevor", key_file=key_file)

    def test_edited_declared_brand_refuses_a_paid_dispatch_without_an_acknowledgement(self):
        self.edited()
        self.assertIn("Dr. Brand", self.refused_reason())
        self.assertTrue(self.dispatch(authority="local")["admitted"])   # recorded, not refused

    def test_signed_acknowledgement_admits_and_records_stale_pins(self):
        new = self.edited()
        self.ack(new)
        decision = self.dispatch()
        row, = decision["out_of_pipeline"]["input_changed"]
        self.assertEqual((row["path"], row["old_sha256"], row["new_sha256"]),
                         ("Dr. Brand", sha(self.BRAND), sha(new)))
        self.assertEqual(row["stale_brand_pins"], {"launch.json": sha(self.BRAND)})
        self.assertEqual(decision["out_of_pipeline"]["content_mismatch"], [])

    def test_acknowledgement_is_void_when_the_file_changes_again(self):
        new = self.edited()
        self.ack(new)
        self.write("Dr. Brand", json.dumps({"brand_id": "b", "palette": {"x": 99}}))
        self.assertIn("Dr. Brand", self.refused_reason())

    def test_acknowledgement_for_a_different_hash_is_ignored(self):
        new = self.edited()
        self.ack(new)
        path = self.run_root / "private" / "input-acknowledgements.json"
        doc = json.loads(path.read_text())
        doc["entries"][0]["new_sha256"] = sha("some other brand")
        path.write_text(json.dumps(doc))
        self.assertIn("Dr. Brand", self.refused_reason())

    def test_unsigned_or_foreign_key_acknowledgement_is_ignored(self):
        new = self.edited()
        self.ack(new, key_file=self.make_key(OTHER_KEY, "other"))
        self.assertIn("Dr. Brand", self.refused_reason())
        path = self.run_root / "private" / "input-acknowledgements.json"
        doc = json.loads(path.read_text())
        doc["entries"][0].pop("signature")
        path.write_text(json.dumps(doc))
        self.assertIn("Dr. Brand", self.refused_reason())

    def test_acknowledgement_cannot_be_made_for_a_wrong_old_or_new_hash(self):
        new = self.edited()
        with self.assertRaises(ValueError):
            self.ack(new, old=sha("not the registered hash"))
        with self.assertRaises(ValueError):
            governed_runner.acknowledge_input(self.run_root, "Dr. Brand", old_sha256=sha(self.BRAND),
                                              new_sha256=sha("not on disk"), reason="r", approver="T")

    def test_acknowledge_input_command(self):
        import quarantine_ledger
        new = self.edited()
        rc = quarantine_ledger.main(["acknowledge-input", "--run", str(self.run_root), "--path", "Dr. Brand",
                                     "--old-sha256", sha(self.BRAND), "--new-sha256", sha(new),
                                     "--reason", "r", "--approver", "T"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.dispatch()["admitted"])

    def test_a_file_the_intake_does_not_name_refuses(self):
        self.govern("Other Brand", "intake", self.BRAND)
        self.write("Other Brand", json.dumps({"brand_id": "b", "palette": {"x": 2}}))
        self.assertIn("Other Brand", self.refused_reason())

    def test_named_brand_that_is_not_a_brand_profile_refuses(self):
        self.govern("Dr. Brand", "intake", self.BRAND)
        self.write("Dr. Brand", json.dumps({"palette": {}}))
        self.assertIn("Dr. Brand", self.refused_reason())
        (self.run_root / "Dr. Brand").write_bytes(b"\x89PNG\x00\x01")
        self.assertIn("Dr. Brand", self.refused_reason())

    def test_brand_registered_to_another_stage_or_in_a_folder_refuses(self):
        self.govern("Dr. Brand", "copy", self.BRAND)
        self.write("Dr. Brand", json.dumps({"brand_id": "b", "palette": {"x": 3}}))
        self.assertIn("Dr. Brand", self.refused_reason())
        (self.run_root / "intake.json").write_text(
            json.dumps({"brand_file": "copy/Dr. Brand"}), encoding="utf-8")
        self.assertEqual(oop.declared_brand_input(self.run_root, oop.load(self.run_root)["outputs"]), None)


class TestOwnerDerivation(Helpers):
    def setUp(self):
        super().setUp()
        self.mob = {"mobile-tablet/section-03.png": "mobile three", "mobile-tablet/wireframe.pdf": "mpdf"}
        self.desk = {"desktop-wireframe/section-01.png": "desk one"}
        self.receipt("mobile-tablet", self.mob)
        self.receipt("desktop-wireframe", self.desk)

    def stale_copy(self, rel, now_text, owner="intake"):
        self.govern(rel, owner, "an older body")
        self.write(rel, now_text)

    def test_byte_copy_of_a_pass_receipt_artifact_no_longer_takes_an_owner(self):
        # 1.3.47: byte equality with a receipt hash is a claim about content, not a receipt
        # listing this exact path. The dispatch refuses until the operator signs a reown.
        self.stale_copy("review-pdfs/s03.png", "mobile three")
        self.assertIn("review-pdfs/s03.png", self.refused_reason())
        governed_runner.reown(self.run_root, "review-pdfs/s03.png", owner_stage="mobile-tablet",
                              reason="byte copy of the mobile-tablet closed output", approver="Trevor")
        decision = self.dispatch("desktop-wireframe")
        row, = decision["out_of_pipeline"]["superseded_mismatch"]
        self.assertEqual((row["owner_stage"], row["registered_owner"]), ("mobile-tablet", "intake"))
        self.assertIn("signed reown", row["owner_basis"])
        self.assertTrue(self.dispatch("mobile-tablet")["admitted"])

    def test_owner_stays_upstream_of_a_later_dispatch(self):
        self.stale_copy("review-pdfs/s03.png", "mobile three")
        self.assertIn("review-pdfs/s03.png", self.refused_reason("visual-mockup"))

    def test_same_bytes_outside_a_shared_directory_keep_the_registry_owner(self):
        self.stale_copy("stray-copy.png", "mobile three")
        self.stale_copy("mobile-tablet-copy/s03.png", "mobile three")
        reason = self.refused_reason()
        self.assertIn("stray-copy.png", reason)
        self.assertIn("mobile-tablet-copy/s03.png", reason)

    def test_bytes_in_no_receipt_keep_the_registry_owner(self):
        self.stale_copy("review-pdfs/unknown.png", "bytes no receipt knows")
        self.assertIn("review-pdfs/unknown.png", self.refused_reason())

    def test_a_failed_stage_receipt_proves_nothing(self):
        self.receipt("mobile-tablet", self.mob, status="fail")
        self.stale_copy("review-pdfs/s03.png", "mobile three")
        self.assertIn("review-pdfs/s03.png", self.refused_reason())

    def test_sidecar_citing_receipt_hashes_proves_nothing(self):
        board = json.dumps({"board": "b.png", "output_sha256": sha("board png"), "sections": [
            {"images": [{"sha256": sha("desk one")}, {"sha256": sha("mobile three")}]}]})
        self.stale_copy("review-pdfs/b.json", board)
        self.stale_copy("review-pdfs/b.png", "board png")
        reason = self.refused_reason()
        self.assertIn("review-pdfs/b.json", reason)
        self.assertIn("review-pdfs/b.png", reason)

    def test_path_listed_in_a_pass_receipt_takes_that_stage_as_owner(self):
        self.receipt("mobile-tablet", dict(self.mob, **{"review-pdfs/b.json": "recorded board"}))
        self.stale_copy("review-pdfs/b.json", "board edited since")
        decision = self.dispatch("desktop-wireframe")
        row, = decision["out_of_pipeline"]["superseded_mismatch"]
        self.assertEqual(row["owner_stage"], "mobile-tablet")
        self.assertIn("pass receipt", row["owner_basis"])
        self.assertIn("review-pdfs/b.json", self.refused_reason("visual-mockup"))

    def test_sidecar_citing_nothing_refuses(self):
        self.stale_copy("review-pdfs/b.json", json.dumps({"board": "b.png"}))
        self.assertIn("review-pdfs/b.json", self.refused_reason())

    def test_board_image_with_a_sibling_claiming_its_hash_refuses(self):
        board = json.dumps({"board": "b.png", "output_sha256": sha("tampered board png"),
                            "sections": [{"sha256": sha("mobile three")}]})
        self.stale_copy("review-pdfs/b.json", board)
        self.stale_copy("review-pdfs/b.png", "tampered board png")
        self.assertIn("review-pdfs/b.png", self.refused_reason())

    def test_upstream_receipt_path_still_blocks_a_later_dispatch_but_not_its_own(self):
        self.receipt("desktop-wireframe", dict(self.desk, **{"review-pdfs/d.json": "recorded"}))
        self.stale_copy("review-pdfs/d.json", "edited")
        self.assertTrue(self.dispatch("desktop-wireframe")["admitted"])
        self.assertIn("review-pdfs/d.json", self.refused_reason("mobile-tablet"))


class TestQuarantineCollision(Helpers):
    DW = "desktop-wireframe"

    def quarantined(self, rel, text="old working file"):
        self.write(rel, text)
        governed_runner.quarantine(self.run_root, rel, reason="working file", approver="Trevor")

    def release(self, rel, stage=DW, **kw):
        return governed_runner.release_quarantine(self.run_root, rel, stage=stage,
                                                  reason="stage regenerated it", approver="Trevor", **kw)

    def test_own_path_registers_and_closes_only_through_a_signed_release_over_new_bytes(self):
        paths = ("production-request-desktop-wireframe.json", "desktop-wireframe/copy-bands.json")
        for rel in paths:
            self.quarantined(rel)
        decision = self.dispatch(self.DW)
        rows = {r["path"]: r["owner_stage"] for r in decision["out_of_pipeline"]["quarantined_to_supersede"]}
        self.assertEqual(rows, dict.fromkeys(paths, self.DW))        # information only
        for rel in paths:
            for call in (governed_runner.register_output, governed_runner.close_output):
                with self.assertRaises(ValueError):                  # the admission releases nothing
                    call(self.run_root, rel, stage=self.DW)
            with self.assertRaises(ValueError):                      # still the quarantined bytes
                self.release(rel)
            self.write(rel, "regenerated by the stage")
            self.release(rel)
            governed_runner.register_output(self.run_root, rel, stage=self.DW)
            governed_runner.close_output(self.run_root, rel, stage=self.DW)
        result = governed_runner.scan(self.run_root)
        self.assertEqual({e["path"] for e in result["governed"]}, set(paths))
        self.assertEqual(result["content_mismatch"], [])

    def test_registered_path_that_was_never_regenerated_cannot_be_closed_even_with_a_given_hash(self):
        self.quarantined("desktop-wireframe/a.json")
        self.dispatch(self.DW)
        old = oop._sha256_file(self.run_root / "desktop-wireframe/a.json")
        for sha_arg in (old, "a" * 64):
            with self.assertRaises(ValueError):
                governed_runner.register_output(self.run_root, "desktop-wireframe/a.json", stage=self.DW)
            with self.assertRaises(ValueError):
                governed_runner.close_output(self.run_root, "desktop-wireframe/a.json",
                                             stage=self.DW, sha256=sha_arg)

    def test_quarantined_path_outside_the_stage_scope_cannot_be_released(self):
        self.quarantined("mobile-tablet/copy-bands.json")
        self.quarantined("copy/notes.md")
        self.dispatch(self.DW)
        for rel in ("mobile-tablet/copy-bands.json", "copy/notes.md"):
            self.write(rel, "regenerated")
            for stage in (self.DW, "mobile-tablet", "copy"):
                if governed_runner.in_stage_scope(rel, stage):
                    continue
                with self.assertRaises(ValueError):
                    self.release(rel, stage)
                with self.assertRaises(ValueError):
                    governed_runner.register_output(self.run_root, rel, stage=stage)

    def test_release_is_for_its_own_stage_only(self):
        self.quarantined("mobile-tablet/copy-bands.json")
        self.write("mobile-tablet/copy-bands.json", "regenerated")
        self.release("mobile-tablet/copy-bands.json", "mobile-tablet")
        governed_runner.register_output(self.run_root, "mobile-tablet/copy-bands.json", stage="mobile-tablet")
        with self.assertRaises(ValueError):
            governed_runner.register_output(self.run_root, "mobile-tablet/copy-bands.json", stage=self.DW)

    def test_no_signed_release_means_no_register_for_a_rewritten_file(self):
        self.quarantined("desktop-wireframe/a.json")
        self.write("desktop-wireframe/a.json", "rewritten with no release")
        for call in (governed_runner.register_output, governed_runner.close_output):
            with self.assertRaises(ValueError):
                call(self.run_root, "desktop-wireframe/a.json", stage=self.DW)

    def test_a_refused_or_non_paid_admission_releases_nothing(self):
        self.quarantined("desktop-wireframe/a.json")
        self.govern("copy/c.md", "copy", "old")
        self.write("copy/c.md", "changed upstream")
        with self.assertRaises(governed_runner.AdmissionRefused):
            self.dispatch(self.DW)
        self.assertTrue(self.dispatch(self.DW, authority="local")["admitted"])
        with self.assertRaises(ValueError):
            governed_runner.register_output(self.run_root, "desktop-wireframe/a.json", stage=self.DW)

    def test_registered_generated_image_still_cannot_be_quarantined(self):
        self.govern("image-generation-qc/a.png", "image-generation-qc")
        with self.assertRaises(ValueError):
            governed_runner.quarantine(self.run_root, "image-generation-qc/a.png", reason="hide", approver="T")
        self.quarantined("desktop-wireframe/a.json")
        self.write("desktop-wireframe/a.json", "new bytes")
        self.release("desktop-wireframe/a.json")
        governed_runner.register_output(self.run_root, "desktop-wireframe/a.json", stage=self.DW)
        governed_runner.close_output(self.run_root, "desktop-wireframe/a.json", stage=self.DW)
        with self.assertRaises(ValueError):              # now governed: cannot be re-quarantined
            governed_runner.quarantine(self.run_root, "desktop-wireframe/a.json", reason="hide", approver="T")

    def test_scope_helpers(self):
        self.assertTrue(governed_runner.in_stage_scope("review-pdfs/x.png", "desktop-wireframe"))
        self.assertTrue(governed_runner.in_stage_scope("production-request-mobile-tablet.json", "mobile-tablet"))
        self.assertFalse(governed_runner.in_stage_scope("production-request-mobile-tablet.json", "desktop-wireframe"))
        self.assertFalse(governed_runner.in_stage_scope("mobile-tablet-extra/x", "mobile-tablet"))
        self.assertEqual(governed_runner.shared_output_dirs(), ("review-pdfs/",))


if __name__ == "__main__":
    unittest.main()
