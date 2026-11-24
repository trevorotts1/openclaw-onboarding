#!/usr/bin/env python3
"""SWB-240 (1.3.47): admission v3 under THREAT MODEL M.

M: the actor can WRITE ANY FILE inside the run folder (governor.json, any
stage-executor-record.json, sidecar JSON, the ledger, edited images) but does NOT hold the
operator key. Only key-signed records and the gate's pass-stage receipts are trusted.

Ported from the two independent attack runs:
  SWB-220 attack run (A1..A7)  -> class A below
  SWB-231 attack run (B01..B22 incl. B08, B09, B10, B14b, B19, B20) -> class B below
Each ATTACK test PASSES when the attack is REFUSED (a FAIL means it succeeded). The TWIN and
INTENDED tests pin each new signed condition one at a time and the admitted cases.
Throwaway keys only (the fixture KEY / OTHER_KEY). Run: python3 tests/test_swb240_attacks.py
"""
import json
import os
import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import governed_runner as GR  # noqa: E402
import quarantine_ledger  # noqa: E402
from test_quarantine_supersede import KEY, OTHER_KEY  # noqa: E402
from test_runstate_owner_collision import LEDGER, REQ, RESULT, Helpers, sha  # noqa: E402

oop = GR.detector()
DW = "desktop-wireframe"
IMG = b"\x89PNG off-pipeline generated image"
REL = "desktop-wireframe/section-02.png"
HERO = "image-generation-qc/hero.png"


class Base240(Helpers):
    def refuses(self, fn, *a, **k):
        try:
            fn(*a, **k)
        except (ValueError, GR.AdmissionRefused):
            return True
        return False

    def hide(self, rel=REL, data=IMG):
        p = self.run_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        GR.quarantine(self.run_root, rel, reason="x", approver="T")
        return p

    def gov(self):
        return json.loads((self.run_root / "private/governor.json").read_text())

    def put_gov(self, doc):
        (self.run_root / "private/governor.json").write_text(json.dumps(doc))

    def forge_exec(self, stage_dir, rel, data):
        rec = self.run_root / stage_dir / "stage-executor-record.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(json.dumps({"stage": stage_dir, "generated_at":
                                   (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),
                                   "images": [{"file": rel, "sha256": oop.hashlib.sha256(data).hexdigest()}]}))
        t = (datetime.now(timezone.utc) + timedelta(seconds=5)).timestamp()
        os.utime(rec, (t, t))

    def launder(self, p, rel=REL, stage=DW, data=IMG + b"\x00"):
        """The attacker's whole move: rewrite the bytes, register, close. True when REFUSED and
        the path is not governed afterwards."""
        p.write_bytes(data)
        self.refuses(GR.register_output, self.run_root, rel, stage=stage)
        closed = not self.refuses(GR.close_output, self.run_root, rel, stage=stage)
        governed = rel in [e["path"] for e in GR.scan(self.run_root)["governed"]]
        return not closed and not governed

    def regenerated(self, rel=REL, stage=DW, text="freshly rendered"):
        """What the operator sees: the stage rewrote the path; the operator signs the release."""
        self.write(rel, text)
        return GR.release_quarantine(self.run_root, rel, stage=stage, reason="stage regenerated it",
                                     approver="Trevor")

    def read_json(self, rel):
        return json.loads((self.run_root / rel).read_text())

    def write_json(self, rel, doc):
        (self.run_root / rel).write_text(json.dumps(doc))


# ======================================================================================
# A: the SWB-220 attack run
# ======================================================================================
class A(Base240):
    def q(self, rel, text):
        self.write(rel, text)
        GR.quarantine(self.run_root, rel, reason="off-pipeline", approver="T")

    def test_A1_quarantined_image_laundered_by_one_byte(self):
        p = self.hide()
        self.dispatch(DW)
        self.assertTrue(self.launder(p), "ATTACK SUCCEEDED: quarantined image +1 byte closed as governed")

    def test_A2_runstate_lookalikes(self):
        for rel in ("sub/production-request.json", "production-request.json.bak",
                    "Production-Request.json", "page-result .json"):
            self.govern(rel, "intake", REQ if "request" in rel.lower() else RESULT)
            self.write(rel, json.dumps({"model": "evil", "sections": [], "request_id": 1,
                                        "status": 1, "artifacts": [], "calls": []}))
        r = self.refused_reason()
        for rel in ("sub/production-request.json", "production-request.json.bak",
                    "Production-Request.json", "page-result .json"):
            self.assertIn(rel, r)

    def test_A3_outside_scope(self):
        self.q("image-generation-qc/x.png", "img")
        self.q("copy/public-copy.md", "copy")
        self.dispatch(DW)
        for rel in ("image-generation-qc/x.png", "copy/public-copy.md"):
            self.write(rel, "regenerated")
            for st in (DW, "image-generation-qc", "copy"):
                if GR.in_stage_scope(rel, st):
                    continue
                self.assertTrue(self.refuses(GR.release_quarantine, self.run_root, rel, stage=st,
                                             reason="r", approver="T"), rel + st)
                self.assertTrue(self.refuses(GR.register_output, self.run_root, rel, stage=st), rel + st)

    def test_A4_reuse_admission(self):
        self.q("desktop-wireframe/a.json", "old")
        self.dispatch(DW)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "desktop-wireframe/a.json",
                                     stage="mobile-tablet"))
        self.q("desktop-wireframe/b.json", "b")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "desktop-wireframe/b.json", stage=DW))

    def test_A5_forged_unsigned_admission_releases_nothing(self):
        self.hide(HERO, b"\x89PNG hidden generated image")
        led = oop._ledger_entry(self.run_root, HERO)
        self.dispatch("intake")
        doc = self.gov()
        doc["admitted"].append({"admitted": True, "authority": "paid_dispatch", "stage": "copy",
            "out_of_pipeline": {"quarantine_ledger_sha256": oop._sha256_file(oop.ledger_path(self.run_root)),
                "quarantined_to_supersede": [{"path": HERO, "owner_stage": "copy", "sha256": led["sha256"]}]}})
        self.put_gov(doc)
        (self.run_root / HERO).write_bytes(b"\x89PNG hidden generated image\x00")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, HERO, stage="copy"))
        self.assertTrue(self.refuses(GR.close_output, self.run_root, HERO, stage="copy"))

    def test_A6_owner_claim_by_citation(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        self.govern("review-pdfs/intake-notes.json", "intake", json.dumps({"note": "orig"}))
        self.write("review-pdfs/intake-notes.json",
                   json.dumps({"note": "ARBITRARY NEW CONTENT", "x": {"sha256": sha("mobile three")}}))
        self.assertTrue(self.refuses(self.dispatch, DW),
                        "ATTACK SUCCEEDED: intake-owned review JSON with a cited hash was admitted")

    def test_A6b_board_image_replaced(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        self.govern("review-pdfs/b.json", "intake", "{}")
        self.govern("review-pdfs/b.png", "intake", "orig board")
        self.write("review-pdfs/b.png", "ANY IMAGE")
        self.write("review-pdfs/b.json", json.dumps({"board": "b.png", "output_sha256": sha("ANY IMAGE"),
                                                     "s": [{"sha256": sha("mobile three")}]}))
        self.assertTrue(self.refuses(self.dispatch, DW),
                        "ATTACK SUCCEEDED: arbitrary board image + self-made sidecar superseded")

    def test_A7_bytes_not_in_receipt(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        self.govern("review-pdfs/s.png", "intake", "old")
        self.write("review-pdfs/s.png", "mobile three!")
        self.assertIn("review-pdfs/s.png", self.refused_reason())
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three!"}, status="fail")
        self.assertIn("review-pdfs/s.png", self.refused_reason())


# ======================================================================================
# B: the SWB-231 attack run
# ======================================================================================
class B(Base240):
    # ---- admission records ---------------------------------------------------
    def test_B01_unsigned_forged_admission(self):
        self.hide()
        led = oop._ledger_entry(self.run_root, REL)
        self.dispatch("intake")
        doc = self.gov()
        doc["admitted"].append({"admitted": True, "authority": "paid_dispatch", "stage": DW,
            "out_of_pipeline": {"quarantine_ledger_sha256": oop._sha256_file(oop.ledger_path(self.run_root)),
                "quarantined_to_supersede": [{"path": REL, "owner_stage": DW, "sha256": led["sha256"]}]}})
        self.put_gov(doc)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_B02_foreign_key_admission(self):
        self.hide()
        led = oop._ledger_entry(self.run_root, REL)
        self.dispatch("intake")
        doc = self.gov()
        row = {"admitted": True, "authority": "paid_dispatch", "stage": DW,
               "out_of_pipeline": {"quarantine_ledger_sha256": oop._sha256_file(oop.ledger_path(self.run_root)),
                   "quarantined_to_supersede": [{"path": REL, "owner_stage": DW, "sha256": led["sha256"]}]}}
        oop.sign_admission(self.run_root, row, key_file=self.make_key(OTHER_KEY, "o"))
        doc["admitted"].append(row)
        self.put_gov(doc)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_B03_signed_row_edited_stage_and_path(self):
        self.hide()
        self.hide(HERO, b"\x89PNG other")
        self.dispatch(DW)
        doc = self.gov()
        row = [r for r in doc["admitted"] if r.get("stage") == DW][-1]
        row["stage"] = "image-generation-qc"
        row["out_of_pipeline"]["quarantined_to_supersede"][0].update(
            path=HERO, owner_stage="image-generation-qc", sha256=oop._ledger_entry(self.run_root, HERO)["sha256"])
        self.put_gov(doc)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, HERO, stage="image-generation-qc"))

    def test_B04_refused_signed_row_moved_to_admitted(self):
        self.hide()
        self.govern("copy/public-copy.md", "copy", "c")
        self.write("copy/public-copy.md", "changed")
        self.assertTrue(self.refuses(self.dispatch, DW))
        doc = self.gov()
        row = doc["refused"][-1]
        row["admitted"] = True
        doc["admitted"].append(row)
        self.put_gov(doc)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_B05_replay_after_new_quarantine(self):
        self.hide()
        self.dispatch(DW)
        self.hide("desktop-wireframe/section-03.png", b"\x89PNG second")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "desktop-wireframe/section-03.png", stage=DW))

    def test_B06_replay_into_another_run_with_other_bytes(self):
        self.hide()
        self.dispatch(DW)
        self.regenerated()                                  # a REAL signed release in run A
        other = Path(self.tmp.name) / "runB"
        shutil.copytree(self.run_root, other)
        (other / REL).write_bytes(IMG + b"\x00")            # but run B holds other bytes
        self.assertTrue(self.refuses(GR.register_output, other, REL, stage=DW))
        self.assertTrue(self.refuses(GR.close_output, other, REL, stage=DW))

    # ---- old image + 1 byte ----------------------------------------------------
    def test_B07_old_image_plus_one_byte_no_record(self):
        p = self.hide()
        self.dispatch(DW)
        self.assertTrue(self.launder(p))

    def test_B08_forged_executor_record_own_stage(self):
        p = self.hide()
        self.dispatch(DW)
        self.forge_exec(DW, REL, IMG + b"\x00")
        self.assertTrue(self.launder(p), "ATTACK SUCCEEDED: hand-written stage-executor-record.json bound old image+1 byte")

    def test_B09_forged_executor_record_other_stage_dir(self):
        p = self.hide()
        self.dispatch(DW)
        self.forge_exec("copy", REL, IMG + b"\x00")
        self.assertTrue(self.launder(p), "ATTACK SUCCEEDED: executor record in ANOTHER stage dir bound the path")

    def test_B10_edit_existing_executor_record(self):
        p = self.hide()
        self.dispatch(DW)
        self.render("desktop-wireframe/other.png", "real render", DW)
        rec = self.run_root / DW / "stage-executor-record.json"
        d = json.loads(rec.read_text())
        d["images"].append({"file": REL, "sha256": oop.hashlib.sha256(IMG + b"\x00").hexdigest()})
        st = rec.stat()
        rec.write_text(json.dumps(d))
        os.utime(rec, (st.st_atime, st.st_mtime))
        self.assertTrue(self.launder(p), "ATTACK SUCCEEDED: edited real executor record bound old image+1 byte")

    # ---- receipts / boards -----------------------------------------------------
    def test_B11_receipt_hash_reused_for_other_path_closes_nothing(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        self.govern("review-pdfs/x.png", "intake", "orig")
        self.write("review-pdfs/x.png", "mobile three")
        # 1.3.47: byte equality with a receipt hash is no longer an owner; it blocks the dispatch
        self.assertTrue(self.refuses(self.dispatch, DW))
        self.assertIn("review-pdfs/x.png", [e["path"] for e in GR.scan(self.run_root)["content_mismatch"]])
        self.assertNotIn("review-pdfs/x.png", [e["path"] for e in GR.scan(self.run_root)["governed"]])

    def test_B12_board_png_swap_with_sibling_json_edit(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        for n, t in (("b.json", "{}"), ("b.png", "orig board")):
            self.govern("review-pdfs/" + n, "intake", t)
        self.write("review-pdfs/b.png", "SWAPPED")
        self.write("review-pdfs/b.json", json.dumps({"board": "b.png", "output_sha256": sha("SWAPPED"),
            "sha256": sha("mobile three"), "artifact_hashes": {"review-pdfs/b.png": sha("SWAPPED")}}))
        self.assertTrue(self.refuses(self.dispatch, DW))

    def test_B13_board_swap_when_receipt_lists_path(self):
        self.receipt("mobile-tablet", {"review-pdfs/b.png": "orig board"})
        self.govern("review-pdfs/b.png", "intake", "orig board")
        self.write("review-pdfs/b.png", "ANY IMAGE")
        self.dispatch(DW)           # the receipt-listed path names mobile-tablet: downstream, superseded for dispatch
        self.assertIn("review-pdfs/b.png", [e["path"] for e in GR.scan(self.run_root)["content_mismatch"]])
        self.assertNotIn("review-pdfs/b.png", [e["path"] for e in GR.scan(self.run_root)["governed"]])
        self.assertTrue(self.refuses(self.dispatch, "visual-mockup"))

    # ---- input acknowledgement -------------------------------------------------
    def brand_setup(self, BF="brand-profile.json"):
        self.BF = BF
        brand = json.dumps({"brand_id": "b"})
        (self.run_root / "intake.json").write_text(json.dumps(
            {"page_kind": "sales", "copy_version": "standard", "brand_file": BF}))
        self.govern(BF, "intake", brand)
        return brand

    def test_B14_ack_for_other_hash(self):
        brand = self.brand_setup()
        self.write(self.BF, json.dumps({"brand_id": "evil"}))
        self.assertTrue(self.refuses(GR.acknowledge_input, self.run_root, self.BF, old_sha256=sha(brand),
                                     new_sha256=sha("x"), reason="r", approver="T"))
        self.assertTrue(self.refuses(self.dispatch, DW))

    def test_B15_ack_then_change_again(self):
        brand = self.brand_setup()
        new = json.dumps({"brand_id": "ok"})
        self.write(self.BF, new)
        GR.acknowledge_input(self.run_root, self.BF, old_sha256=sha(brand), new_sha256=sha(new),
                             reason="r", approver="T")
        self.assertTrue(self.dispatch(DW)["admitted"])               # intended admitted case
        self.write(self.BF, json.dumps({"brand_id": "evil"}))
        self.assertTrue(self.refuses(self.dispatch, DW))

    def test_B16_ack_forged_unsigned_foreign_key_and_edited(self):
        brand = self.brand_setup()
        new = json.dumps({"brand_id": "ok"})
        self.write(self.BF, new)
        ackf = self.run_root / "private/input-acknowledgements.json"
        e = {"path": self.BF, "old_sha256": sha(brand), "new_sha256": sha(new), "reason": "r",
             "approver": "T", "acknowledged_at": datetime.now(timezone.utc).isoformat()}
        ackf.write_text(json.dumps({"entries": [e]}))
        self.assertTrue(self.refuses(self.dispatch, DW))
        e["signature"] = oop._ack_signature(e, OTHER_KEY)
        ackf.write_text(json.dumps({"entries": [e]}))
        self.assertTrue(self.refuses(self.dispatch, DW))
        GR.acknowledge_input(self.run_root, self.BF, old_sha256=sha(brand), new_sha256=sha(new),
                             reason="r", approver="T")
        d = json.loads(ackf.read_text())
        d["entries"][-1]["new_sha256"] = sha("other")
        self.write(self.BF, "other")
        ackf.write_text(json.dumps(d))
        self.assertTrue(self.refuses(self.dispatch, DW))

    def test_B17_ack_misused_for_other_authorities(self):
        self.brand_setup()
        self.write(self.BF, "changed")
        for auth in ("installation", "publishing"):
            self.assertTrue(self.refuses(self.dispatch, DW, auth))

    def test_B14b_brand_file_named_brand_json_edit(self):
        self.brand_setup("brand.json")
        self.write("brand.json", json.dumps({"brand_id": "evil"}))
        self.assertTrue(self.refuses(self.dispatch, DW),
                        "ATTACK SUCCEEDED: brand_file=brand.json (a STAGE_INPUTS name) edited, dispatch admitted")

    # ---- ledger edits ----------------------------------------------------------
    def test_B18_ledger_entry_sha_edited(self):
        self.hide()
        self.dispatch(DW)
        doc = self.ledger()
        doc["entries"][0]["sha256"] = sha("nothing")
        self.save_ledger(doc)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_B19_ledger_entry_deleted_then_registered(self):
        p = self.hide()
        doc = self.ledger()
        doc["entries"] = []
        self.save_ledger(doc)
        p.write_bytes(IMG + b"\x00")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW)
                        or self.refuses(GR.close_output, self.run_root, REL, stage=DW),
                        "ATTACK SUCCEEDED: deleting the ledger entry let the hidden image register+close")
        self.assertTrue(self.launder(p))

    def test_B19b_ledger_file_deleted(self):
        p = self.hide()
        oop.ledger_path(self.run_root).unlink()
        self.assertTrue(self.launder(p))

    def test_B20_ledger_file_replaced_to_match_admission(self):
        p = self.hide()
        self.dispatch(DW)
        old = (self.run_root / "private/quarantine-ledger.json").read_bytes()
        later = self.hide("desktop-wireframe/section-09.png", b"\x89PNG later")
        (self.run_root / "private/quarantine-ledger.json").write_bytes(old)    # roll the ledger back
        self.assertTrue(self.refuses(GR.register_output, self.run_root,
                                     "desktop-wireframe/section-09.png", stage=DW))
        self.assertTrue(self.launder(later, "desktop-wireframe/section-09.png", data=b"\x89PNG later+"))

    # ---- key swaps and modes ---------------------------------------------------
    def test_B21_key_swap_env(self):
        self.hide()
        self.dispatch(DW)
        self.regenerated()
        os.environ["SF_PIN_AUTHORITY_KEY_FILE"] = str(self.make_key(OTHER_KEY, "swap"))
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_B22_key_modes(self):
        self.hide()
        self.dispatch(DW)
        self.regenerated()
        loose = self.make_key(KEY, "loose")
        loose.chmod(0o644)
        inside = self.run_root / "k"
        inside.write_bytes(KEY)
        inside.chmod(0o600)
        short = self.make_key(b"short", "short")
        for k in (loose, inside, short, Path(self.tmp.name) / "missing"):
            os.environ["SF_PIN_AUTHORITY_KEY_FILE"] = str(k)
            self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW), str(k))
        os.environ.pop("SF_PIN_AUTHORITY_KEY_FILE")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_B_INTENDED_signed_release_closes(self):
        self.hide()
        self.dispatch(DW)
        self.regenerated()
        GR.register_output(self.run_root, REL, stage=DW)
        self.assertEqual(GR.close_output(self.run_root, REL, stage=DW)["sha256"], sha("freshly rendered"))
        self.assertIn(REL, [e["path"] for e in GR.scan(self.run_root)["governed"]])


# ======================================================================================
# Twins and intended cases for the two new signed records and the seal
# ======================================================================================
class Twins(Base240):
    def setUp(self):
        super().setUp()
        self.hide()
        self.dispatch(DW)

    # ---- release-quarantine ----------------------------------------------------
    def test_unsigned_release_refused(self):
        self.write(REL, "freshly rendered")
        entry = {"path": REL, "sha256": sha("freshly rendered"), "stage": DW, "reason": "r",
                 "approver": "T", "signed_at": datetime.now(timezone.utc).isoformat(), "note": "n"}
        self.write_json("private/quarantine-releases.json", {"entries": [entry]})
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))
        entry["signature"] = "0" * 64
        self.write_json("private/quarantine-releases.json", {"entries": [entry]})
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))
        self.assertTrue(self.refuses(GR.close_output, self.run_root, REL, stage=DW))

    def test_release_for_another_hash_refused(self):
        self.regenerated()
        self.write(REL, "someone rewrote it after the owner signed")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))
        self.assertTrue(self.refuses(GR.close_output, self.run_root, REL, stage=DW))
        self.write(REL, "freshly rendered")                      # back to the signed bytes: valid again
        GR.register_output(self.run_root, REL, stage=DW)
        self.write(REL, "freshly rendered AND changed after registering")
        self.assertTrue(self.refuses(GR.close_output, self.run_root, REL, stage=DW))

    def test_release_edited_after_signing_refused(self):
        self.regenerated()
        doc = self.read_json("private/quarantine-releases.json")
        doc["entries"][0]["sha256"] = sha("whatever bytes the attacker now holds")
        self.write_json("private/quarantine-releases.json", doc)
        self.write(REL, "whatever bytes the attacker now holds")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_release_for_another_path_refused(self):
        other = "desktop-wireframe/section-05.png"
        self.hide(other, b"\x89PNG five")
        self.regenerated(REL)
        self.write(other, "freshly rendered")                     # SAME bytes, other path
        self.assertTrue(self.refuses(GR.register_output, self.run_root, other, stage=DW))
        doc = self.read_json("private/quarantine-releases.json")
        doc["entries"][0]["path"] = other                          # or re-pointed by hand
        self.write_json("private/quarantine-releases.json", doc)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, other, stage=DW))

    def test_release_for_another_stage_refused(self):
        shared = "review-pdfs/MOBILE_WIREFRAMES.pdf"
        self.hide(shared, b"%PDF old")
        self.write(shared, "%PDF regenerated")
        GR.release_quarantine(self.run_root, shared, stage="mobile-tablet", reason="r", approver="T")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, shared, stage=DW))
        doc = self.read_json("private/quarantine-releases.json")
        doc["entries"][-1]["stage"] = DW                           # re-pointed by hand
        self.write_json("private/quarantine-releases.json", doc)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, shared, stage=DW))
        doc["entries"][-1]["stage"] = "mobile-tablet"
        self.write_json("private/quarantine-releases.json", doc)
        GR.register_output(self.run_root, shared, stage="mobile-tablet")

    def test_release_signed_with_another_key_refused(self):
        self.write(REL, "freshly rendered")
        with self.assertRaises(ValueError):                  # the tool will not sign under a foreign key
            GR.release_quarantine(self.run_root, REL, stage=DW, reason="r", approver="T",
                                  key_file=self.make_key(OTHER_KEY, "other"))
        entry = {"run": oop.run_identity(self.run_root),   # 1.3.48: records name their run
                 "path": REL, "sha256": sha("freshly rendered"), "stage": DW, "reason": "r",
                 "approver": "T", "signed_at": datetime.now(timezone.utc).isoformat(), "note": "n"}
        entry["signature"] = oop._record_signature(oop.RELEASE_KIND, oop.RELEASE_FIELDS, entry, OTHER_KEY)
        self.write_json("private/quarantine-releases.json", {"entries": [entry]})   # hand-forged
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))
        self.assertTrue(self.refuses(GR.close_output, self.run_root, REL, stage=DW))
        entry["signature"] = oop._record_signature(oop.RELEASE_KIND, oop.RELEASE_FIELDS, entry, KEY)
        self.write_json("private/quarantine-releases.json", {"entries": [entry]})   # sanity: the real key admits
        GR.register_output(self.run_root, REL, stage=DW)

    def test_release_cannot_reuse_another_records_signature(self):
        self.regenerated()
        doc = self.read_json("private/quarantine-releases.json")
        entry = doc["entries"][0]
        led = oop._ledger_entry(self.run_root, REL)
        entry["sha256"] = sha("other bytes")
        entry["signature"] = led["signature"]                      # the ledger entry's tag
        self.write_json("private/quarantine-releases.json", doc)
        self.write(REL, "other bytes")
        self.assertTrue(self.refuses(GR.register_output, self.run_root, REL, stage=DW))

    def test_release_for_unchanged_quarantined_bytes_refused(self):
        self.write(REL, IMG.decode("latin-1"))                     # not the exact bytes (encoding)
        (self.run_root / REL).write_bytes(IMG)
        with self.assertRaises(ValueError):
            GR.release_quarantine(self.run_root, REL, stage=DW, reason="r", approver="T")

    def test_release_needs_the_stage_to_own_the_path_and_a_reason(self):
        self.write(REL, "freshly rendered")
        with self.assertRaises(ValueError):
            GR.release_quarantine(self.run_root, REL, stage="copy", reason="r", approver="T")
        with self.assertRaises(ValueError):
            GR.release_quarantine(self.run_root, REL, stage=DW, reason="", approver="T")
        with self.assertRaises(ValueError):
            GR.release_quarantine(self.run_root, "desktop-wireframe/never-quarantined.png",
                                  stage=DW, reason="r", approver="T")

    def test_release_note_prints_the_executor_row_as_evidence_only(self):
        self.render(REL, "freshly rendered", DW)
        entry = GR.release_quarantine(self.run_root, REL, stage=DW, reason="r", approver="T")
        self.assertIn("stage-executor-record.json lists " + REL, entry["note"])
        self.assertIn("equals", entry["note"])
        self.assertIn("unsigned", entry["note"])
        # a forged row that names the wrong hash changes the note but never the decision
        self.forge_exec(DW, REL, b"not the bytes")
        entry = GR.release_quarantine(self.run_root, REL, stage=DW, reason="r", approver="T")
        self.assertIn("does NOT equal", entry["note"])

    def test_released_path_is_governed_only_after_register_and_close(self):
        self.regenerated()
        result = GR.scan(self.run_root)
        self.assertIn(REL, [e["path"] for e in result["ungoverned"]])      # still not credit
        GR.register_output(self.run_root, REL, stage=DW)
        GR.close_output(self.run_root, REL, stage=DW)
        self.assertIn(REL, [e["path"] for e in GR.scan(self.run_root)["governed"]])
        self.assertTrue(self.dispatch(DW)["admitted"])

    # ---- reown -----------------------------------------------------------------
    def board(self):
        self.receipt("mobile-tablet", {"mobile-tablet/s.png": "mobile three"})
        self.govern("review-pdfs/MOBILE_WIREFRAMES.pdf.manifest.json", "intake", "{}")
        self.write("review-pdfs/MOBILE_WIREFRAMES.pdf.manifest.json", "{\"rebuilt\": 1}")
        return "review-pdfs/MOBILE_WIREFRAMES.pdf.manifest.json"

    def test_unowned_changed_review_file_refuses_then_signed_reown_admits(self):
        rel = self.board()
        self.assertIn(rel, self.refused_reason())
        entry = GR.reown(self.run_root, rel, owner_stage="mobile-tablet",
                         reason="rebuilt by the mobile-tablet stage; see its pass receipt", approver="Trevor")
        self.assertIn("registry owner 'intake'", entry["note"])
        decision = self.dispatch(DW)
        row, = decision["out_of_pipeline"]["superseded_mismatch"]
        self.assertEqual((row["path"], row["owner_stage"]), (rel, "mobile-tablet"))

    def test_reown_with_a_stale_sha_refused(self):
        rel = self.board()
        GR.reown(self.run_root, rel, owner_stage="mobile-tablet", reason="r", approver="T")
        self.write(rel, "{\"rebuilt\": 2}")                        # bytes moved on after signing
        self.assertIn(rel, self.refused_reason())

    def test_reown_signed_with_another_key_or_unsigned_refused(self):
        rel = self.board()
        GR.reown(self.run_root, rel, owner_stage="mobile-tablet", reason="r", approver="T",
                 key_file=self.make_key(OTHER_KEY, "other"))
        self.assertIn(rel, self.refused_reason())
        GR.reown(self.run_root, rel, owner_stage="mobile-tablet", reason="r", approver="T")
        doc = self.read_json("private/reown-records.json")
        doc["entries"][0].pop("signature")
        self.write_json("private/reown-records.json", doc)
        self.assertIn(rel, self.refused_reason())

    def test_reown_edited_after_signing_or_signature_borrowed_refused(self):
        rel = self.board()
        GR.reown(self.run_root, rel, owner_stage="mobile-tablet", reason="r", approver="T")
        doc = self.read_json("private/reown-records.json")
        doc["entries"][0]["owner_stage"] = DW                       # a different owner than signed
        self.write_json("private/reown-records.json", doc)
        self.assertIn(rel, self.refused_reason("mobile-tablet"))
        self.regenerated()                                          # a release signature as a reown tag
        rel_sig = self.read_json("private/quarantine-releases.json")["entries"][0]["signature"]
        doc["entries"][0]["owner_stage"] = "mobile-tablet"
        doc["entries"][0]["signature"] = rel_sig
        self.write_json("private/reown-records.json", doc)
        self.assertIn(rel, self.refused_reason())

    def test_reown_to_an_upstream_stage_still_blocks_and_needs_a_registered_file(self):
        rel = self.board()
        GR.reown(self.run_root, rel, owner_stage="copy", reason="r", approver="T")
        self.assertIn(rel, self.refused_reason())                   # copy is upstream of the dispatch
        with self.assertRaises(ValueError):
            GR.reown(self.run_root, "review-pdfs/not-registered.json", owner_stage=DW, reason="r", approver="T")
        with self.assertRaises(ValueError):
            GR.reown(self.run_root, rel, owner_stage="not-a-stage", reason="r", approver="T")

    def test_receipt_listed_exact_path_still_derives_the_owner(self):
        self.receipt("mobile-tablet", {"review-pdfs/b.json": "recorded board"})
        self.govern("review-pdfs/b.json", "intake", "old")
        self.write("review-pdfs/b.json", "edited since")
        row, = self.dispatch(DW)["out_of_pipeline"]["superseded_mismatch"]
        self.assertEqual(row["owner_stage"], "mobile-tablet")
        self.assertIn("pass receipt", row["owner_basis"])

    # ---- the seal --------------------------------------------------------------
    def test_full_rollback_of_ledger_and_seal_is_caught_by_the_anchor(self):
        led = (self.run_root / "private/quarantine-ledger.json").read_bytes()
        seal = (self.run_root / "private/quarantine-seal.json").read_bytes()
        later = self.hide("desktop-wireframe/section-09.png", b"\x89PNG later")
        (self.run_root / "private/quarantine-ledger.json").write_bytes(led)
        (self.run_root / "private/quarantine-seal.json").write_bytes(seal)
        self.assertTrue(self.launder(later, "desktop-wireframe/section-09.png", data=b"\x89PNG later+"))

    def test_deleted_seal_or_forged_seal_refuses_everything(self):
        (self.run_root / "private/quarantine-seal.json").unlink()
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "desktop-wireframe/new.json", stage=DW))
        self.assertTrue(self.refuses(self.dispatch, DW))
        GR.seal_ledger(self.run_root)                               # the operator re-adopts it
        GR.register_output(self.run_root, "desktop-wireframe/new.json", stage=DW)
        doc = self.read_json("private/quarantine-seal.json")
        doc["entries"] = []
        self.write_json("private/quarantine-seal.json", doc)
        self.assertTrue(self.refuses(GR.register_output, self.run_root, "desktop-wireframe/new2.json", stage=DW))

    def test_sealing_a_ledger_with_a_forged_entry_is_refused(self):
        doc = self.ledger()
        doc["entries"][0]["reason"] = "edited"
        self.save_ledger(doc)
        with self.assertRaises(ValueError):
            GR.seal_ledger(self.run_root)

    def test_pre_1_3_47_ledger_without_a_seal_needs_one_seal_command(self):
        (self.run_root / "private/quarantine-seal.json").unlink()
        self.assertEqual(quarantine_ledger.main(["seal", "--run", str(self.run_root)]), 0)
        self.assertTrue(self.dispatch(DW)["admitted"])

    # ---- cli -------------------------------------------------------------------
    def test_cli_release_and_reown(self):
        self.write(REL, "freshly rendered")
        self.assertEqual(quarantine_ledger.main(
            ["release-quarantine", "--run", str(self.run_root), "--path", REL, "--stage", DW,
             "--reason", "regenerated", "--approver", "Trevor"]), 0)
        GR.register_output(self.run_root, REL, stage=DW)
        GR.close_output(self.run_root, REL, stage=DW)
        self.govern("review-pdfs/x.json", "intake", "{}")
        self.write("review-pdfs/x.json", "{\"a\": 1}")
        self.assertEqual(quarantine_ledger.main(
            ["reown", "--run", str(self.run_root), "--path", "review-pdfs/x.json",
             "--owner-stage", DW, "--reason", "rebuilt by this stage", "--approver", "Trevor"]), 0)
        self.assertEqual(quarantine_ledger.main(
            ["release-quarantine", "--run", str(self.run_root), "--path", REL, "--stage", "copy",
             "--reason", "r", "--approver", "T"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
