#!/usr/bin/env python3
"""SWB-250 (1.3.48): run binding, absent-seal refusal and the signed rebind record, under THREAT MODEL M.

M: the actor can WRITE ANY FILE inside the run folder but does NOT hold the operator key.

The bar for this chain (SKILL.md, SOP, CHANGELOG): the pre-existing admission design (unsigned
governed-outputs.json registry, keyless register_output/close_output, directory scanning that
skips symlinked dirs) is a KNOWN BASELINE LIMITATION, recorded as a follow-up (a separate
hardening that signs the registry). It is NOT tested here. This file covers:
  N05  deleting BOTH quarantine-ledger.json and quarantine-seal.json while the operator's
       anchor outside the run exists must refuse, never read as "never quarantined"
  N07  a ledger, seal and release record signed for run A must be void in run B
       (and a replay twin for every record kind: entry, seal, release, reown, acknowledgement,
       rebind, admission row)
  absent-seal twins, a pre-1.3.48 ledger adoption set, and the rebind twin set
       (wrong hash, other path, other run, foreign key, unsigned).
Every ATTACK test PASSES when the attack is REFUSED; on 1.3.47 these tests fail (the attacks
succeed or the new API is absent). Throwaway keys only. Run: python3 tests/test_swb250_attacks.py
"""
import hmac
import json
import os
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
from test_runstate_owner_collision import Helpers, sha  # noqa: E402

oop = GR.detector()
DW = "desktop-wireframe"
IMG = b"\x89PNG off-pipeline generated image"
REL = "desktop-wireframe/section-02.png"
COPY = "copy/public-copy.md"
COPY2 = "copy/other-copy.md"


class Base250(Helpers):
    def refuses(self, fn, *a, **k):
        try:
            fn(*a, **k)
        except (ValueError, GR.AdmissionRefused):
            return True
        return False

    def hide(self, root=None, rel=REL, data=IMG):
        root = root or self.run_root
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        GR.quarantine(root, rel, reason="x", approver="T")
        return p

    def governed(self, rel, root=None):
        return rel in [e["path"] for e in GR.scan(root or self.run_root)["governed"]]

    def admitted(self, stage=DW, root=None):
        try:
            return GR.admit(root or self.run_root, kind="direct_executor",
                            authority="paid_dispatch", stage=stage)["admitted"]
        except GR.AdmissionRefused:
            return False

    def refusal_source(self, stage=DW, root=None):
        try:
            GR.admit(root or self.run_root, kind="direct_executor", authority="paid_dispatch",
                     stage=stage)
        except GR.AdmissionRefused as exc:
            return exc.decision.get("source")
        return None

    def other_run(self, name="other"):
        """A second run folder that is a byte-for-byte copy of this one (the replay vehicle)."""
        dest = Path(self.tmp.name) / name
        shutil.copytree(self.run_root, dest)
        return dest

    def set_run_id(self, value, root=None):
        path = (root or self.run_root) / "private" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"run_id": value, "stages": {}, "receipts": {}}), encoding="utf-8")

    def anchor_dir(self):
        return self.key.parent / "sf-seal-anchors"

    def edited_copy(self, text="v2 edited by the owner"):
        self.govern(COPY, "copy", "v1 attested")
        self.write(COPY, text)
        return sha(text)


# ---------------------------------------------------------------- run identity

class TestRunIdentity(Base250):
    def test_identity_names_the_root_and_the_state_run_id(self):
        self.assertEqual(oop.run_identity(self.run_root),
                         {"root": str(self.run_root.resolve()), "run_id": ""})
        self.set_run_id("run-abc")
        self.assertEqual(oop.run_identity(self.run_root)["run_id"], "run-abc")

    def test_every_signed_record_carries_the_run_inside_the_signed_payload(self):
        self.set_run_id("run-abc")
        ident = oop.run_identity(self.run_root)
        self.hide()
        self.assertEqual(oop._ledger_entry(self.run_root, REL)["run"], ident)
        self.assertEqual(json.loads((self.run_root / oop.SEAL_FILE).read_text())["run"], ident)
        self.write(REL, "regenerated")
        self.assertEqual(GR.release_quarantine(self.run_root, REL, stage=DW, reason="r",
                                               approver="T")["run"], ident)
        self.govern("review-pdfs/b.json", "intake", "v1")
        self.write("review-pdfs/b.json", "v2")
        self.assertEqual(GR.reown(self.run_root, "review-pdfs/b.json", owner_stage="intake",
                                  reason="r", approver="T")["run"], ident)
        self.edited_copy()
        self.assertEqual(GR.rebind(self.run_root, COPY, stage="copy", reason="r",
                                   approver="T")["run"], ident)
        self.govern("brand.json", "intake", "b1")
        self.write("brand.json", "b2")
        self.assertEqual(GR.acknowledge_input(self.run_root, "brand.json", old_sha256=sha("b1"),
                                              new_sha256=sha("b2"), reason="r",
                                              approver="T")["run"], ident)

    def test_admission_rows_carry_the_run_inside_the_signed_payload(self):
        self.set_run_id("run-abc")
        decision = self.dispatch("copy")
        self.assertEqual(decision["run_binding"], oop.run_identity(self.run_root))
        self.assertTrue(oop.verify_admission(decision, KEY, root=self.run_root))

    def test_editing_the_run_field_of_a_record_voids_it(self):
        self.hide()
        doc = json.loads((self.run_root / oop.LEDGER_FILE).read_text())
        doc["entries"][0]["run"] = {"root": "/somewhere/else", "run_id": ""}
        (self.run_root / oop.LEDGER_FILE).write_text(json.dumps(doc))
        result = GR.scan(self.run_root)
        self.assertEqual(result["quarantined"], [])
        self.assertIn(REL, [e["path"] for e in result["ungoverned"]])


# ---------------------------------------------------------------- N07 and the replay twins

class TestReplayBetweenRuns(Base250):
    def test_N07_release_replayed_from_another_run_is_void(self):
        self.hide()
        self.write(REL, "reviewed render")
        GR.release_quarantine(self.run_root, REL, stage=DW, reason="r", approver="Trevor")
        other = self.other_run()
        self.assertIsNone(oop.find_release(other, REL, DW, GR.in_stage_scope))
        self.assertTrue(self.refuses(GR.register_output, other, REL, stage=DW))
        self.assertTrue(self.refuses(GR.close_output, other, REL, stage=DW))
        self.assertFalse(self.governed(REL, other))
        self.assertFalse(self.admitted(root=other))

    def test_N07_original_run_still_admits_its_own_release(self):    # the positive twin
        self.hide()
        self.write(REL, "reviewed render")
        GR.release_quarantine(self.run_root, REL, stage=DW, reason="r", approver="Trevor")
        GR.register_output(self.run_root, REL, stage=DW)
        GR.close_output(self.run_root, REL, stage=DW)
        self.assertTrue(self.governed(REL))
        self.assertTrue(self.admitted())

    def test_N07_ledger_and_seal_replayed_from_another_run_are_void(self):
        self.hide()
        other = self.other_run()
        status = oop._ledger_status(other)
        self.assertFalse(status["ok"])
        self.assertTrue("another run" in status["why"] or "anchor" in status["why"], status["why"])
        scan = GR.scan(other)
        self.assertIn("quarantine_ledger_error", scan)
        self.assertEqual(scan["quarantined"], [])

    def test_N07_seal_alone_replayed_with_a_matching_ledger_is_void(self):
        """Replace the other run's ledger+seal with this run's: the seal names this run, not that one."""
        self.hide()
        other = self.other_run()
        for name in ("quarantine-ledger.json", "quarantine-seal.json"):
            shutil.copy(self.run_root / "private" / name, other / "private" / name)
        self.assertFalse(oop._ledger_status(other)["ok"])

    def test_N07_reown_replayed_from_another_run_is_void(self):
        self.govern("review-pdfs/b.json", "intake", "v1")
        self.write("review-pdfs/b.json", "v2")
        GR.reown(self.run_root, "review-pdfs/b.json", owner_stage=DW, reason="r", approver="T")
        self.assertEqual(oop.reowned_to(self.run_root, "review-pdfs/b.json", sha("v2")), DW)
        other = self.other_run()
        self.assertIsNone(oop.reowned_to(other, "review-pdfs/b.json", sha("v2")))
        self.assertFalse(self.admitted(root=other))

    def test_N07_input_acknowledgement_replayed_from_another_run_is_void(self):
        self.govern("brand.json", "intake", "b1")
        self.write("brand.json", "b2")
        GR.acknowledge_input(self.run_root, "brand.json", old_sha256=sha("b1"),
                             new_sha256=sha("b2"), reason="r", approver="T")
        row = {"path": "brand.json", "registered": sha("b1"), "actual": sha("b2")}
        self.assertTrue(oop.input_acknowledged(self.run_root, row))
        self.assertFalse(oop.input_acknowledged(self.other_run(), row))

    def test_N07_rebind_replayed_from_another_run_is_void(self):
        digest = self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="Trevor")
        other = self.other_run()
        self.assertIsNone(oop.rebound_record(other, COPY, digest, oop.load(other)["outputs"][COPY]))
        self.assertEqual([e["path"] for e in GR.scan(other)["content_mismatch"]], [COPY])

    def test_N07_admission_row_replayed_from_another_run_is_void(self):
        decision = self.dispatch("copy")
        other = self.other_run()
        self.assertTrue(oop.verify_admission(decision, KEY, root=self.run_root))
        self.assertFalse(oop.verify_admission(decision, KEY, root=other))
        decision["run_binding"] = oop.run_identity(other)           # relabelling breaks the signature
        self.assertFalse(oop.verify_admission(decision, KEY, root=other))

    def test_same_path_new_run_id_voids_every_record(self):
        """A run folder recreated at the same path (new gate run_id) inherits nothing."""
        self.set_run_id("run-one")
        self.hide()
        self.write(REL, "reviewed render")
        GR.release_quarantine(self.run_root, REL, stage=DW, reason="r", approver="T")
        digest = self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])
        self.set_run_id("run-two")
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertIsNone(oop.find_release(self.run_root, REL, DW, GR.in_stage_scope))
        self.assertIsNone(oop.rebound_record(self.run_root, COPY, digest,
                                             oop.load(self.run_root)["outputs"][COPY]))

    def test_deleting_state_json_voids_records_never_forges_them(self):
        self.set_run_id("run-one")
        self.hide()
        (self.run_root / "private" / "state.json").unlink()
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])


# ---------------------------------------------------------------- N05 and the absent-seal twins

class TestAbsentLedgerAndSeal(Base250):
    def test_N05_deleting_ledger_and_seal_does_not_forget_the_quarantine(self):
        p = self.hide()
        (self.run_root / oop.LEDGER_FILE).unlink()
        (self.run_root / oop.SEAL_FILE).unlink()
        self.assertTrue(self.anchor_dir().is_dir(), "the operator's anchor sits outside the run")
        p.write_bytes(IMG + b"\x01")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))
        self.assertTrue(self.refuses(GR.close_output, self.run_root, REL, stage=DW))
        self.assertFalse(self.governed(REL))
        self.assertFalse(self.admitted())

    def test_N05_cannot_verify_is_refuse_even_with_no_stray_file(self):
        p = self.hide()
        (self.run_root / oop.LEDGER_FILE).unlink()
        (self.run_root / oop.SEAL_FILE).unlink()
        p.unlink()
        self.assertFalse(self.admitted(), "an unverifiable quarantine ledger is never 'nothing quarantined'")
        self.assertEqual(self.refusal_source(), "quarantine_ledger")

    def test_N05_status_names_the_anchor(self):
        self.hide()
        (self.run_root / oop.LEDGER_FILE).unlink()
        (self.run_root / oop.SEAL_FILE).unlink()
        status = oop._ledger_status(self.run_root)
        self.assertFalse(status["ok"])
        self.assertIn("anchor", status["why"])

    def test_absent_seal_with_the_ledger_present_refuses(self):
        self.hide()
        (self.run_root / oop.SEAL_FILE).unlink()
        status = oop._ledger_status(self.run_root)
        self.assertFalse(status["ok"])
        self.assertFalse(self.admitted())

    def test_unreadable_seal_refuses(self):
        self.hide()
        (self.run_root / oop.SEAL_FILE).write_text("{not json", encoding="utf-8")
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertFalse(self.admitted())

    def test_absent_ledger_with_the_seal_present_refuses(self):
        self.hide()
        (self.run_root / oop.LEDGER_FILE).unlink()
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertFalse(self.admitted())

    def test_unreadable_ledger_refuses(self):
        self.hide()
        (self.run_root / oop.LEDGER_FILE).write_text("[[", encoding="utf-8")
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])
        self.assertFalse(self.admitted())

    def test_unreadable_anchor_refuses(self):
        self.hide()
        for f in self.anchor_dir().glob("*.json"):
            f.write_text("garbage")
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])

    def test_control_a_run_never_quarantined_is_admitted(self):    # the negative twin
        self.assertFalse(self.anchor_dir().exists())
        self.assertTrue(self.admitted("copy"))
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])

    def test_control_an_intact_ledger_and_seal_are_honoured(self):
        self.hide()
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])
        self.assertEqual([e["path"] for e in GR.scan(self.run_root)["quarantined"]], [REL])
        self.assertTrue(self.admitted("copy"))

    def test_the_anchor_is_created_only_by_the_operator_signed_writers(self):
        """scan, register, close, admit, delivery and status never create the anchor."""
        self.govern(COPY, "copy", "v1")
        GR.scan(self.run_root)
        GR.delivery(self.run_root, [{"path": COPY}])
        quarantine_ledger.main(["status", "--run", str(self.run_root)])
        self.assertFalse(self.anchor_dir().exists())
        self.admitted("copy")    # 1.3.50: the governor's signed admission row is a signing writer
        self.assertTrue(any(self.anchor_dir().glob("*.json")))
        shutil.rmtree(self.anchor_dir())
        (self.run_root / "private" / "governor.json").unlink()
        self.write("stray.png", "stray")
        GR.quarantine(self.run_root, "stray.png", reason="r", approver="T")    # operator-signed writer
        self.assertTrue(any(self.anchor_dir().glob("*.json")))

    def test_seal_subcommand_refuses_to_invent_a_ledger(self):
        self.assertTrue(self.refuses(GR.seal_ledger, self.run_root))
        self.assertFalse(self.anchor_dir().exists())

    def test_seal_cannot_rebuild_a_deleted_ledger(self):
        self.hide()
        (self.run_root / oop.LEDGER_FILE).unlink()
        (self.run_root / oop.SEAL_FILE).unlink()
        self.assertTrue(self.refuses(GR.seal_ledger, self.run_root))


# ---------------------------------------------------------------- pre-1.3.48 ledger adoption

class TestLegacyAdoption(Base250):
    def legacy_ledger(self):
        """Rewrite the ledger and seal exactly as 1.3.47 wrote them (no run field)."""
        p = self.hide()
        ledger = json.loads((self.run_root / oop.LEDGER_FILE).read_text())
        for entry in ledger["entries"]:
            entry.pop("run")
            entry["signature"] = oop._legacy_entry_signature(entry, KEY)
        (self.run_root / oop.LEDGER_FILE).write_text(json.dumps(ledger))
        seal = json.loads((self.run_root / oop.SEAL_FILE).read_text())
        seal.pop("run")
        seal["entries"] = sorted(([e["path"], e["signature"]] for e in ledger["entries"]))
        body = {"kind": oop.SEAL_KIND, "serial": seal["serial"], "sealed_at": seal["sealed_at"],
                "entries": seal["entries"]}
        seal["signature"] = hmac.new(KEY, oop._canonical_json(body), oop.hashlib.sha256).hexdigest()
        (self.run_root / oop.SEAL_FILE).write_text(json.dumps(seal))
        return p

    def test_a_1_3_47_ledger_honours_nothing_until_adopted(self):
        self.legacy_ledger()
        status = oop._ledger_status(self.run_root)
        self.assertFalse(status["ok"])
        self.assertIn("adopt-legacy", status["why"])
        self.assertFalse(self.admitted())

    def test_seal_without_the_flag_does_not_adopt(self):
        self.legacy_ledger()
        self.assertTrue(self.refuses(GR.seal_ledger, self.run_root))
        self.assertFalse(oop._ledger_status(self.run_root)["ok"])

    def test_adopt_legacy_binds_the_entries_to_this_run(self):
        self.legacy_ledger()
        result = GR.seal_ledger(self.run_root, adopt_legacy=True)
        self.assertEqual(result["adopted"], 1)
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])
        self.assertEqual([e["path"] for e in GR.scan(self.run_root)["quarantined"]], [REL])
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_adopt_legacy_refuses_an_entry_whose_file_changed(self):
        p = self.legacy_ledger()
        p.write_bytes(IMG + b"\x09")
        self.assertTrue(self.refuses(GR.seal_ledger, self.run_root, adopt_legacy=True))

    def test_adopt_legacy_refuses_a_forged_legacy_entry(self):
        self.legacy_ledger()
        ledger = json.loads((self.run_root / oop.LEDGER_FILE).read_text())
        ledger["entries"][0]["signature"] = "0" * 64
        (self.run_root / oop.LEDGER_FILE).write_text(json.dumps(ledger))
        self.assertTrue(self.refuses(GR.seal_ledger, self.run_root, adopt_legacy=True))

    def test_adopt_legacy_through_the_command_line(self):
        self.legacy_ledger()
        self.assertEqual(quarantine_ledger.main(["seal", "--run", str(self.run_root),
                                                 "--adopt-legacy", "--yes"]), 0)
        self.assertTrue(oop._ledger_status(self.run_root)["ok"])

    def test_a_pre_1_3_48_release_record_is_void(self):
        self.hide()
        self.write(REL, "reviewed")
        entry = {"path": REL, "sha256": sha("reviewed"), "stage": DW, "reason": "r",
                 "approver": "T", "signed_at": "2026-11-24T00:00:00+00:00", "note": "n"}
        legacy_fields = tuple(f for f in oop.RELEASE_FIELDS if f != "run")
        entry["signature"] = oop._record_signature(oop.RELEASE_KIND, legacy_fields, entry, KEY)
        (self.run_root / oop.RELEASE_FILE).write_text(json.dumps({"entries": [entry]}))
        self.assertIsNone(oop.find_release(self.run_root, REL, DW, GR.in_stage_scope))
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))


# ---------------------------------------------------------------- the rebind record

class TestRebind(Base250):
    def records(self):
        return json.loads((self.run_root / oop.REBIND_FILE).read_text())

    def put_records(self, doc):
        (self.run_root / oop.REBIND_FILE).write_text(json.dumps(doc))

    def mismatched(self, rel=COPY):
        return [e["path"] for e in GR.scan(self.run_root)["content_mismatch"]] == [rel]

    def test_without_a_record_the_changed_copy_file_is_a_mismatch(self):
        self.edited_copy()
        self.assertTrue(self.mismatched())
        self.assertFalse(self.admitted())

    def test_a_signed_rebind_re_attests_the_changed_copy_file(self):
        digest = self.edited_copy()
        entry = GR.rebind(self.run_root, COPY, stage="copy", reason="owner rewrote the headline",
                          approver="Trevor")
        self.assertEqual(entry["sha256"], digest)
        self.assertEqual(entry["old_sha256"], sha("v1 attested"))
        self.assertEqual(entry["stage"], "copy")
        self.assertEqual(entry["run"], oop.run_identity(self.run_root))
        result = GR.scan(self.run_root)
        self.assertEqual(result["content_mismatch"], [])
        self.assertTrue(self.governed(COPY))
        self.assertEqual(result["rebound"][0]["approver"], "Trevor")
        self.assertTrue(self.admitted())

    def test_the_admission_decision_lists_the_rebound_file_as_an_owner_decision(self):
        digest = self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="why", approver="Trevor")
        rows = self.dispatch()["out_of_pipeline"]["rebound"]
        self.assertEqual(rows[0]["path"], COPY)
        self.assertEqual(rows[0]["new_sha256"], digest)
        self.assertEqual(rows[0]["old_sha256"], sha("v1 attested"))
        self.assertEqual(rows[0]["approver"], "Trevor")
        self.assertIn("owner decision", rows[0]["basis"])
        self.assertIn("not a pipeline pass", rows[0]["basis"])

    def test_the_rebound_file_is_delivered_not_excluded(self):
        self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        split = GR.delivery(self.run_root, [{"path": COPY}])
        self.assertEqual([e["path"] for e in split["admitted"]], [COPY])

    def test_the_note_prints_the_gate_written_evidence_and_trusts_none_of_it(self):
        self.edited_copy()
        self.receipt("copy", {COPY: "v1 attested"})
        (self.run_root / "private" / "state.json").write_text(json.dumps({
            "run_id": "r1", "stages": {"copy": {"closed_outputs": {COPY: sha("v1 attested")}}},
            "receipts": {}}))
        entry = GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        note = entry["note"]
        self.assertIn(sha("v1 attested"), note)
        self.assertIn("state.json", note)
        self.assertIn("receipts: copy (pass) lists sha256=" + sha("v1 attested"), note)
        self.assertIn("trusted for nothing", note)
        self.assertIn("owner decision", note)

    def test_the_command_line_prints_the_evidence_and_the_owner_decision(self):
        self.edited_copy()
        rc = quarantine_ledger.main(["rebind", "--run", str(self.run_root), "--path", COPY,
                                     "--stage", "copy", "--reason", "r", "--approver", "T"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.governed(COPY))

    # ---- wrong hash
    def test_wrong_hash_file_changed_after_signing_is_void(self):
        self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        self.write(COPY, "v3 changed again")
        self.assertTrue(self.mismatched())
        self.assertFalse(self.governed(COPY))
        self.assertFalse(self.admitted())

    def test_wrong_hash_record_edited_to_cover_new_bytes_is_void(self):
        self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        self.write(COPY, "v3 changed again")
        doc = self.records()
        doc["entries"][0]["sha256"] = sha("v3 changed again")
        self.put_records(doc)
        self.assertTrue(self.mismatched())

    def test_stale_old_hash_is_void(self):
        """The registry was re-attested after the record: the record named another old hash."""
        self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        reg = oop.load(self.run_root)
        reg["outputs"][COPY]["sha256"] = sha("something else attested")
        oop.save(self.run_root, reg)
        self.assertTrue(self.mismatched())

    # ---- other path
    def test_other_path_record_copied_to_a_second_registered_file_is_void(self):
        self.edited_copy()
        self.govern(COPY2, "copy", "v1 attested")
        self.write(COPY2, "v2 edited by the owner")           # the same new bytes
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        doc = self.records()
        doc["entries"].append(dict(doc["entries"][0], path=COPY2))
        self.put_records(doc)
        self.assertEqual([e["path"] for e in GR.scan(self.run_root)["content_mismatch"]], [COPY2])

    def test_rebind_refuses_an_unregistered_path(self):
        self.write("copy/stray.md", "stray")
        self.assertTrue(self.refuses(GR.rebind, self.run_root, "copy/stray.md", stage="copy",
                                     reason="r", approver="T"))

    def test_rebind_cannot_launder_a_quarantined_image(self):
        self.hide()
        self.write(REL, "regenerated")
        self.assertTrue(self.refuses(GR.rebind, self.run_root, REL, stage=DW, reason="r", approver="T"))
        doc = {"entries": [{"run": oop.run_identity(self.run_root), "path": REL,
                            "old_sha256": sha("x"), "sha256": sha("regenerated"), "stage": DW,
                            "reason": "r", "approver": "T", "signed_at": "x", "note": "n",
                            "signature": "0" * 64}]}
        self.put_records(doc)
        self.assertFalse(self.governed(REL))

    def test_rebind_refuses_a_file_that_still_holds_its_attested_bytes(self):
        self.govern(COPY, "copy", "v1")
        self.assertTrue(self.refuses(GR.rebind, self.run_root, COPY, stage="copy", reason="r",
                                     approver="T"))

    def test_rebind_must_name_the_registered_owning_stage(self):
        self.edited_copy()
        self.assertTrue(self.refuses(GR.rebind, self.run_root, COPY, stage=DW, reason="r", approver="T"))

    def test_record_edited_to_another_stage_is_void(self):
        self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        doc = self.records()
        doc["entries"][0]["stage"] = DW
        self.put_records(doc)
        self.assertTrue(self.mismatched())

    def test_record_edited_reason_or_approver_is_void(self):
        self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        for field, value in (("reason", "forged"), ("approver", "Mallory"), ("note", "n2"),
                             ("signed_at", "2026-01-01T00:00:00+00:00")):
            doc = self.records()
            original = doc["entries"][0][field]
            doc["entries"][0][field] = value
            self.put_records(doc)
            self.assertTrue(self.mismatched(), field)
            doc["entries"][0][field] = original
            self.put_records(doc)
        self.assertTrue(self.governed(COPY))              # sanity: restored record is valid again

    # ---- other run
    def test_other_run_record_is_void_here(self):
        self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        doc = self.records()
        doc["entries"][0]["run"] = {"root": "/another/run", "run_id": ""}
        self.put_records(doc)
        self.assertTrue(self.mismatched())

    def test_record_signed_for_another_run_and_copied_in_is_void(self):
        other = Path(self.tmp.name) / "run2"
        other.mkdir()
        (other / "intake.json").write_text((self.run_root / "intake.json").read_text())
        for root in (self.run_root, other):
            self.govern(COPY, "copy", "v1 attested") if root is self.run_root else None
        # run 2 gets the same registered file and the same new bytes
        (other / COPY).parent.mkdir(parents=True, exist_ok=True)
        (other / COPY).write_text("v1 attested", encoding="utf-8")
        GR.register_output(other, COPY, stage="copy")
        GR.close_output(other, COPY, stage="copy")
        (other / COPY).write_text("v2 edited by the owner", encoding="utf-8")
        self.write(COPY, "v2 edited by the owner")
        GR.rebind(other, COPY, stage="copy", reason="r", approver="T")
        shutil.copy(other / oop.REBIND_FILE, self.run_root / oop.REBIND_FILE)
        self.assertTrue(self.mismatched())
        self.assertEqual(GR.scan(other)["content_mismatch"], [])           # valid in its own run

    # ---- foreign key and unsigned
    def test_foreign_key_record_is_void(self):
        self.edited_copy()
        with self.assertRaises(ValueError):    # 1.3.50: a foreign key cannot even anchor the run
            GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="Mallory",
                      key_file=str(self.make_key(OTHER_KEY, "other")))
        self.assertTrue(self.mismatched())
        self.assertFalse(self.governed(COPY))
        self.assertFalse(self.admitted())

    def test_unsigned_record_is_void(self):
        digest = self.edited_copy()
        self.put_records({"entries": [{
            "run": oop.run_identity(self.run_root), "path": COPY, "old_sha256": sha("v1 attested"),
            "sha256": digest, "stage": "copy", "reason": "r", "approver": "T",
            "signed_at": "2026-11-24T00:00:00+00:00", "note": "n"}]})
        self.assertTrue(self.mismatched())
        self.put_records({"entries": [{
            "run": oop.run_identity(self.run_root), "path": COPY, "old_sha256": sha("v1 attested"),
            "sha256": digest, "stage": "copy", "reason": "r", "approver": "T",
            "signed_at": "2026-11-24T00:00:00+00:00", "note": "n", "signature": "0" * 64}]})
        self.assertTrue(self.mismatched())

    def test_another_record_types_signature_does_not_verify_as_a_rebind(self):
        digest = self.edited_copy()
        entry = {"run": oop.run_identity(self.run_root), "path": COPY, "old_sha256": sha("v1 attested"),
                 "sha256": digest, "stage": "copy", "reason": "r", "approver": "T",
                 "signed_at": "2026-11-24T00:00:00+00:00", "note": "n"}
        entry["signature"] = oop._record_signature(oop.REOWN_KIND, oop.REBIND_FIELDS, entry, KEY)
        self.put_records({"entries": [entry]})
        self.assertTrue(self.mismatched())

    def test_no_operator_key_means_no_rebind_is_honoured(self):
        self.edited_copy()
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        saved = os.environ.pop("SF_PIN_AUTHORITY_KEY_FILE")
        try:
            self.assertTrue(self.mismatched())
        finally:
            os.environ["SF_PIN_AUTHORITY_KEY_FILE"] = saved

    def test_rebind_does_not_touch_other_mismatches(self):
        self.edited_copy()
        self.govern(COPY2, "copy", "v1 attested")
        self.write(COPY2, "v2 edited again")
        GR.rebind(self.run_root, COPY, stage="copy", reason="r", approver="T")
        self.assertEqual([e["path"] for e in GR.scan(self.run_root)["content_mismatch"]], [COPY2])
        self.assertFalse(self.admitted())


if __name__ == "__main__":
    unittest.main(verbosity=1)
