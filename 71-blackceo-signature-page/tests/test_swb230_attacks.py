#!/usr/bin/env python3
"""SWB-230 (1.3.46) / SWB-240 (1.3.47): the SWB-220 attack run, ported. Every test PASSES when the attack is REFUSED.

A1, A5, A6, A6b fail on 1.3.45 and pass on 1.3.46; A2, A3, A4, A7 held on 1.3.45 and keep
holding. The twins pin each new condition one at a time. Throwaway keys only (the fixture KEY).
Run: python3 tests/test_swb230_attacks.py
"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import governed_runner as GR  # noqa: E402
from test_quarantine_supersede import OTHER_KEY  # noqa: E402
from test_runstate_owner_collision import LEDGER, REQ, RESULT, Helpers, sha  # noqa: E402

oop = GR.detector()
DW = "desktop-wireframe"


class Attacks(Helpers):
    def q(self, rel, text):
        self.write(rel, text)
        GR.quarantine(self.run_root, rel, reason="off-pipeline", approver="T")

    def refuses(self, fn, *a, **k):
        try:
            fn(*a, **k)
        except (ValueError, GR.AdmissionRefused):
            return True
        return False

    def resign(self, doc, key_bytes=None, mutate=None):
        """Rewrite governor.json the way a forger would, signing with `key_bytes` (or not)."""
        gov = self.run_root / "private" / "governor.json"
        if mutate:
            mutate(doc)
        if key_bytes is not None:
            keyfile = self.make_key(key_bytes, "forger-key")
            for row in doc["admitted"]:
                oop.sign_admission(self.run_root, row, key_file=keyfile)
        gov.write_text(json.dumps(doc), encoding="utf-8")

    def governor(self):
        return json.loads((self.run_root / "private" / "governor.json").read_text())

    # A1 a generated image hidden through quarantine, "superseded" by one trailing byte
    def test_A1_quarantined_image_laundered_by_one_byte(self):
        img = b"\x89PNG off-pipeline generated image"
        p = self.run_root / "desktop-wireframe/section-02.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(img)
        GR.quarantine(self.run_root, "desktop-wireframe/section-02.png", reason="x", approver="T")
        self.dispatch(DW)
        p.write_bytes(img + b"\x00")
        self.assertTrue(self.refuses(GR.register_output, self.run_root,
                                     "desktop-wireframe/section-02.png", stage=DW))
        self.assertTrue(self.refuses(GR.close_output, self.run_root,
                                     "desktop-wireframe/section-02.png", stage=DW))

    # A2 run-state lookalikes
    def test_A2_runstate_lookalikes(self):
        for rel in ("sub/production-request.json", "production-request.json.bak",
                    "Production-Request.json", "page-result .json"):
            self.govern(rel, "intake", REQ if "request" in rel.lower() else RESULT)
            self.write(rel, json.dumps({"model": "evil", "sections": [], "request_id": 1,
                                        "status": 1, "artifacts": [], "calls": []}))
        reason = self.refused_reason()
        for rel in ("sub/production-request.json", "production-request.json.bak",
                    "Production-Request.json", "page-result .json"):
            self.assertIn(rel, reason)

    # A3 register a quarantined path outside the dispatched stage's own scope
    def test_A3_outside_scope_legit(self):
        self.q("image-generation-qc/x.png", "img")
        self.q("copy/public-copy.md", "copy")
        self.dispatch(DW)
        for rel in ("image-generation-qc/x.png", "copy/public-copy.md"):
            for st in (DW, "image-generation-qc", "copy"):
                self.assertTrue(self.refuses(GR.register_output, self.run_root, rel, stage=st), rel + st)

    # A4 reuse an old admission for another stage or another file
    def test_A4_reuse_admission(self):
        self.q("desktop-wireframe/a.json", "old")
        self.dispatch(DW)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "desktop-wireframe/a.json",
                                     stage="mobile-tablet"))
        self.q("desktop-wireframe/b.json", "b")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "desktop-wireframe/b.json",
                                     stage=DW))

    # A5 forged admission record (governor.json used to be unsigned JSON)
    def forged_row(self, rel, stage="copy"):
        led = oop._ledger_entry(self.run_root, rel)
        return {"admitted": True, "authority": "paid_dispatch", "stage": stage,
                "out_of_pipeline": {
                    "quarantine_ledger_sha256": oop._sha256_file(oop.ledger_path(self.run_root)),
                    "quarantined_to_supersede": [{"path": rel, "owner_stage": stage,
                                                  "sha256": led["sha256"]}]}}

    def hidden_image(self, rel="image-generation-qc/hero.png"):
        p = self.run_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG hidden generated image")
        GR.quarantine(self.run_root, rel, reason="x", approver="T")
        return rel

    def attempt_release(self, rel, stage):
        if self.refuses(GR.register_output, self.run_root, rel, stage=stage):
            return False
        (self.run_root / rel).write_bytes(b"\x89PNG hidden generated image\x00")
        return not self.refuses(GR.close_output, self.run_root, rel, stage=stage)

    def test_A5_forged_unsigned_record_releases_nothing(self):
        rel = self.hidden_image()
        doc = {"schema": "x", "admitted": [self.forged_row(rel)], "refused": [], "units": {}}
        (self.run_root / "private").mkdir(exist_ok=True)
        (self.run_root / "private" / "governor.json").write_text(json.dumps(doc))
        self.assertFalse(self.attempt_release(rel, "copy"))

    def test_A5_record_signed_by_another_key_releases_nothing(self):
        rel = self.hidden_image()
        doc = {"schema": "x", "admitted": [self.forged_row(rel)], "refused": [], "units": {}}
        (self.run_root / "private").mkdir(exist_ok=True)
        self.resign(doc, key_bytes=OTHER_KEY)
        self.assertFalse(self.attempt_release(rel, "copy"))

    def test_A5_record_signed_by_the_operator_key_still_needs_the_path_in_stage_scope(self):
        rel = self.hidden_image()                      # image-generation-qc/ is not 'copy' scope
        doc = {"schema": "x", "admitted": [self.forged_row(rel)], "refused": [], "units": {}}
        (self.run_root / "private").mkdir(exist_ok=True)
        gov = self.run_root / "private" / "governor.json"
        gov.write_text(json.dumps(doc))
        for row in doc["admitted"]:
            oop.sign_admission(self.run_root, row)       # the operator key itself, test key
        gov.write_text(json.dumps(doc))
        self.assertFalse(self.attempt_release(rel, "copy"))
        self.assertFalse(self.attempt_release(rel, "image-generation-qc"))   # no row for that stage

    def test_A5_edited_after_signing_releases_nothing(self):
        self.q("desktop-wireframe/a.json", "old")
        self.dispatch(DW)
        doc = self.governor()
        doc["admitted"][-1]["out_of_pipeline"]["quarantined_to_supersede"][0]["owner_stage"] = DW
        doc["admitted"][-1]["item"] = "edited after signing"
        self.resign(doc)
        self.assertFalse(self.attempt_release("desktop-wireframe/a.json", DW))

    def test_signed_record_for_another_stage_releases_nothing(self):
        self.q("mobile-tablet/a.json", "old")
        self.dispatch("mobile-tablet")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "mobile-tablet/a.json", stage=DW))
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "mobile-tablet/a.json", stage="copy"))

    def test_governor_rows_are_signed_and_verify_only_with_the_operator_key(self):
        self.dispatch(DW)
        row = self.governor()["admitted"][-1]
        self.assertTrue(row.get("signature") and row.get("signed_at"))
        self.assertTrue(oop.verify_admission(row, self.key.read_bytes().strip()))
        self.assertFalse(oop.verify_admission(row, OTHER_KEY))
        self.assertFalse(oop.verify_admission(dict(row, stage="copy"), self.key.read_bytes().strip()))

    # A6 owner claim forged inside the file under verification
    def test_A6_owner_claim_by_citation(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        self.govern("review-pdfs/intake-notes.json", "intake", json.dumps({"note": "orig"}))
        self.write("review-pdfs/intake-notes.json",
                   json.dumps({"note": "ARBITRARY NEW CONTENT", "x": {"sha256": sha("mobile three")}}))
        self.assertTrue(self.refuses(self.dispatch, DW))

    # A6b board image replaced, with a sibling JSON claiming its hash
    def test_A6b_board_image_replaced(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        self.govern("review-pdfs/b.json", "intake", "{}")
        self.govern("review-pdfs/b.png", "intake", "orig board")
        self.write("review-pdfs/b.png", "ANY IMAGE")
        self.write("review-pdfs/b.json", json.dumps({"board": "b.png", "output_sha256": sha("ANY IMAGE"),
                                                     "s": [{"sha256": sha("mobile three")}]}))
        self.assertTrue(self.refuses(self.dispatch, DW))

    # A7 bytes that are in no pass receipt
    def test_A7_bytes_not_in_receipt(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        self.govern("review-pdfs/s.png", "intake", "old")
        self.write("review-pdfs/s.png", "mobile three!")
        self.assertIn("review-pdfs/s.png", self.refused_reason())
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three!"}, status="fail")
        self.assertIn("review-pdfs/s.png", self.refused_reason())

    # input change (SWB-220 note: input_changed used to never refuse)
    def test_changed_brand_profile_refuses_a_paid_dispatch_until_acknowledged(self):
        brand = json.dumps({"brand_id": "b"})
        (self.run_root / "intake.json").write_text(json.dumps(
            {"page_kind": "sales", "copy_version": "standard", "brand_file": "Dr. Stephanie Wall"}))
        self.govern("Dr. Stephanie Wall", "intake", brand)
        new = json.dumps({"brand_id": "b", "palette": {"x": 1}})
        self.write("Dr. Stephanie Wall", new)
        self.assertIn("Dr. Stephanie Wall", self.refused_reason())
        GR.acknowledge_input(self.run_root, "Dr. Stephanie Wall", old_sha256=sha(brand),
                             new_sha256=sha(new), reason="owner edit", approver="Trevor")
        self.assertTrue(self.dispatch(DW)["admitted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
