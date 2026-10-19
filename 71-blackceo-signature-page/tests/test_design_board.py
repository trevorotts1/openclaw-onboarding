#!/usr/bin/env python3
"""Design Board (SPF021): contract, QC floor, approval binding, executor and stage gates.

Free: no provider call anywhere; the board PNGs are local fixtures. The read-back check is
exercised two ways: in-process with a double for the OCR reader (bf.fake_ocr), and through the
CLI / executor / stage gate with the real tesseract (skipped where it is not installed).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board_fixture as bf  # noqa: E402

ROOT = bf.ROOT
db = bf.design_board
EXEC = ROOT / "scripts" / "stage_executor.py"
GATE = ROOT / "scripts" / "stage_gate.py"
WRITE_REVIEW = ROOT / "scripts" / "write_review.py"
PY = sys.executable


def run(cmd, env=None):
    return subprocess.run([PY, *map(str, cmd)], text=True, capture_output=True, env=env or bf.subprocess_env())


class Base(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="design-board-test-"))
        self.run_dir = self.td / "run"
        patch = mock.patch.object(db, "ocr_text", bf.fake_ocr)
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def request(self):
        return json.loads((self.run_dir / "production-request.json").read_text(encoding="utf-8"))

    def rewrite_request(self, fn):
        req = self.request()
        fn(req)
        (self.run_dir / "production-request.json").write_text(json.dumps(req), encoding="utf-8")


class ContractTests(Base):
    def test_required_blocks_adapt_per_page_role(self):
        landing = bf.make_run(self.td / "a", "landing")
        thanks = bf.make_run(self.td / "b", "thank_you")
        checkout = bf.make_run(self.td / "c", "checkout")
        got = {}
        for role, rd in (("landing", landing), ("thank_you", thanks), ("checkout", checkout)):
            req = json.loads((rd / "production-request.json").read_text(encoding="utf-8"))
            got[role] = db.plan(rd, req)["expected"]["required_blocks"]
        self.assertIn("aesthetic", got["landing"])
        self.assertIn("banner", got["landing"])
        self.assertIn("size", got["landing"])
        self.assertIn("icons", got["thank_you"])
        self.assertNotIn("aesthetic", got["thank_you"])
        self.assertNotIn("icons", got["checkout"])
        for blocks in got.values():
            for core in ("header", "palette", "typography", "imagery", "cues", "footer"):
                self.assertIn(core, blocks)

    def test_all_seven_page_roles_supported(self):
        schema = json.loads((ROOT / "references" / "page-request.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["page_role"]["enum"]), set(db.ROLE_LABEL))

    def test_prompt_carries_palette_logo_images_and_no_foreign_brand(self):
        bf.make_run(self.run_dir, "landing")
        plan = db.plan(self.run_dir, self.request())
        prompt, sizes = db.compose_prompt(plan, self.request())
        for hexv in ("#1F4E79", "#C8963E", "#9C2F3A", "#F6F1E7", "#222222"):
            self.assertIn(hexv, prompt)
        self.assertIn("Harbor #1F4E79", prompt)
        self.assertIn("Test Client Co", prompt)
        self.assertIn("4 attached", prompt)
        self.assertEqual(len(db.references(plan)), 4)  # logo + the page's three real images
        self.assertNotIn("Set for Life", prompt)
        self.assertNotIn("calm, editorial", prompt)  # the example's aesthetic is not every client's
        self.assertIn("clear, warm, steady", prompt)  # this client's own aesthetic words
        self.assertIn("no picture is drawn from a description", prompt)
        self.assertNotIn("art direction", prompt)
        self.assertEqual(sizes["chars"], len(prompt))

    def test_required_content_is_never_invented(self):
        bf.make_run(self.run_dir, "thank_you", {"icons": []})
        with self.assertRaises(db.BoardError) as cm:
            db.plan(self.run_dir, self.request())
        self.assertIn("icons", str(cm.exception))

    def test_unresolved_brand_colors_refuse(self):
        bf.make_run(self.run_dir, "landing")
        (self.run_dir / "inputs" / "brand.json").write_text(
            json.dumps({"brand_id": "test-client-co", "palette": {"gold": "CLIENT_MUST_SUPPLY"}}))
        with self.assertRaises(db.BoardError):
            db.plan(self.run_dir, self.request())

    def test_example_client_words_refused_on_another_clients_board(self):
        bf.make_run(self.run_dir, "landing", {"positioning_line": "Wealth looks good on you."})
        plan = db.plan(self.run_dir, self.request())
        with self.assertRaises(db.BoardError) as cm:
            db.compose_prompt(plan, self.request())
        self.assertIn("another client", str(cm.exception))

    def test_every_example_board_string_is_refused_on_another_clients_board(self):
        for term in db.EXAMPLE_TERMS:
            self.assertTrue(db.foreign_hits(term.title(), {"brand_name": "Other Co"}), term)
        self.assertEqual(db.foreign_hits("Wealth looks good on you", {"brand_name": "Set For Life Co"}), [])

    def test_content_copied_from_the_example_is_refused(self):
        copies = {"aesthetic_words": ["Chic", "Elevated", "Editorial", "Premium", "Grown"],
                  "icons": ["Workbook", "Quotes", "Presentations", "Conversation", "Growth"],
                  "cues": ["Oversized typography", "Strong hierarchy", "Spacious layout",
                           "No clutter", "Real editorial imagery"],
                  "color_names": {"primary": "Evergreen", "secondary": "Gold", "accent": "Terracotta",
                                  "background": "Ivory"}}
        for key, value in copies.items():
            rd = bf.make_run(self.td / key, "landing", {key: value})
            with self.assertRaises(db.BoardError) as cm:
                db.plan(rd, json.loads((rd / "production-request.json").read_text()))
            self.assertIn("example", str(cm.exception), key)

    def test_a_few_shared_everyday_words_are_not_a_copy(self):
        rd = bf.make_run(self.run_dir, "landing", {"aesthetic_words": ["Elevated", "Warm", "Clear", "Steady", "Calm"],
                                                   "cues": bf.SPEC["cues"][:4] + ["No clutter"]})
        db.plan(rd, self.request())

    def test_color_name_for_a_color_not_in_the_palette_is_refused(self):
        bf.make_run(self.run_dir, "landing", {"color_names": {"primary": "Harbor", "#E2C98F": "Champagne"}})
        with self.assertRaises(db.BoardError) as cm:
            db.plan(self.run_dir, self.request())
        self.assertIn("not in the resolved palette", str(cm.exception))

    def test_the_contract_doc_carries_no_example_clients_content(self):
        doc = (ROOT / "references" / "design-board.md").read_text(encoding="utf-8").lower()
        example = doc.split("## request:", 1)[1].split("## how the board is made", 1)[0]
        for term in db.EXAMPLE_TERMS[1:] + ("champagne", "evergreen", "e2c98f", "chic", "workbook"):
            self.assertNotIn(term, example)


class RealImagesTests(Base):
    """The board is made after the image chain and shows only the page's real images."""

    def test_a_slot_with_no_image_refuses_the_board(self):
        bf.make_run(self.run_dir, "landing", slot_files=1)
        with self.assertRaises(db.BoardError) as cm:
            db.plan(self.run_dir, self.request())
        msg = str(cm.exception)
        self.assertIn("IMG-002", msg)
        self.assertIn("IMG-003", msg)
        self.assertIn("never art-direction stand-ins", msg)

    def test_missing_slot_file_refuses(self):
        bf.make_run(self.run_dir, "landing")
        self.rewrite_request(lambda r: r["sections"][0]["slots"][0].update(file="inputs/nope.png"))
        with self.assertRaises(db.BoardError):
            db.plan(self.run_dir, self.request())

    def test_images_resolve_from_the_pipelines_own_artifacts(self):
        bf.make_run(self.run_dir, "landing", chain=True)
        got = {s["slot_id"]: s for s in db.plan(self.run_dir, self.request())["slots"]}
        self.assertEqual((got["IMG-001"]["origin"], got["IMG-001"]["file"]),
                         ("image-map", "image-generation-qc/Image-001.png"))
        self.assertEqual(got["IMG-002"]["origin"], "image-generation-qc")
        self.assertEqual((got["IMG-003"]["origin"], got["IMG-003"]["source"], got["IMG-003"]["section_id"]),
                         ("inventory", "supplied", "proof"))
        self.assertEqual(got["IMG-002"]["section_id"], "hero")  # the wireframe section plan assigns it

    def test_inventory_slot_with_no_generated_file_yet_refuses(self):
        bf.make_run(self.run_dir, "landing", chain=True)
        (self.run_dir / "image-generation-qc" / "Image-002.png").unlink()
        with self.assertRaises(db.BoardError) as cm:
            db.plan(self.run_dir, self.request())
        self.assertIn("IMG-002", str(cm.exception))

    def test_executor_preflight_counts_every_image_as_attached(self):
        bf.make_run(self.run_dir, "landing", chain=True)
        out = run([EXEC, self.run_dir, "--stages", "design-board", "--preflight"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("refs=4 slots=3", out.stdout)  # logo + 3 images: no tile is left to be drawn

    def test_images_beyond_the_attachment_limit_go_in_one_real_contact_sheet(self):
        bf.make_run(self.run_dir, "landing")
        def many(req):
            slots = [{"slot_id": f"IMG-{i:03d}"} for i in range(1, 17)]
            for i, sl in enumerate(slots, 1):
                bf.png(self.run_dir / "inputs" / f"m{i}.png", (10 * i, 50, 90), (80, 60))
                sl["file"] = f"inputs/m{i}.png"
            req["sections"] = [{"section_id": "all", "section_name": "All", "copy": "x.", "slots": slots}]
        self.rewrite_request(many)
        plan = db.plan(self.run_dir, self.request())
        refs = db.references(plan, self.run_dir)
        self.assertEqual(len(refs), db.MAX_REFERENCES)
        self.assertTrue(refs[-1].endswith("overflow-sheet.png"))
        self.assertEqual(len(db.reference_plan(plan, self.run_dir)[1]), 16 - (db.MAX_REFERENCES - 2))
        self.assertFalse((self.run_dir / db.SHEET_FILE).exists(), "building the plan writes nothing")
        db.build_overflow_sheet(plan, self.run_dir)
        self.assertTrue((self.run_dir / db.SHEET_FILE).is_file())
        prompt, _ = db.compose_prompt(plan, self.request(), self.run_dir)
        self.assertIn("contact sheet of the remaining 4 images", prompt)
        self.assertEqual(db.write_record.__name__, "write_record")

    def test_new_optional_blocks_reach_the_prompt_and_the_read_back_check(self):
        bf.make_run(self.run_dir, "landing", {
            "side_taglines": ["BUILD STEADY", "BUILT FOR FOUNDERS"], "gradient": True,
            "gradient_caption": "A LONG ROAD WELL WALKED", "imagery_extras": [
                {"text": "WORK FIRST. REST AFTER."}, {"file": "inputs/prop.png"}]})
        bf.png(self.run_dir / "inputs" / "prop.png", (200, 100, 50))
        plan = db.plan(self.run_dir, self.request())
        prompt, _ = db.compose_prompt(plan, self.request())
        for text in ("BUILD STEADY", "A LONG ROAD WELL WALKED", "WORK FIRST. REST AFTER.",
                     "1 supplied prop image(s)"):
            self.assertIn(text, prompt)
        self.assertEqual(len(db.references(plan)), 5)  # logo, 3 images, the prop
        bf.seed_board(self.run_dir, approved=False)
        self.assertEqual(db.validate(self.run_dir), [])
        self.assertIn("extra-2", [s["slot_id"] for s in db.load_record(self.run_dir)["image_set"]["slots"]])
        rec = db.load_record(self.run_dir)
        for text in ("A LONG ROAD WELL WALKED", "WORK FIRST. REST AFTER.", "BUILD STEADY"):
            broken = json.loads(json.dumps(rec))
            broken["readback"]["text"] = broken["readback"]["text"].replace(text, "")
            db.save_record(self.run_dir, broken)
            self.assertTrue(any("not legible" in f for f in db.validate(self.run_dir)), text)

    def test_text_tile_and_prop_need_exactly_one_of_text_or_file(self):
        bf.make_run(self.run_dir, "landing", {"imagery_extras": [{"text": "A", "file": "x.png"}]})
        with self.assertRaises(db.BoardError):
            db.plan(self.run_dir, self.request())
        bf.make_run(self.td / "b", "landing", {"imagery_extras": [{"file": "inputs/nope.png"}]})
        with self.assertRaises(db.BoardError):
            db.plan(self.td / "b", json.loads((self.td / "b" / "production-request.json").read_text()))

    def test_gradient_caption_without_the_strip_is_refused(self):
        bf.make_run(self.run_dir, "landing", {"gradient_caption": "A CAPTION"})
        with self.assertRaises(db.BoardError):
            db.plan(self.run_dir, self.request())


class QcAndApprovalTests(Base):
    def seeded(self, **kw):
        bf.make_run(self.run_dir, kw.pop("role", "landing"), chain=kw.pop("chain", False))
        bf.seed_board(self.run_dir, **kw)

    def test_passes_with_approval(self):
        self.seeded()
        self.assertEqual(db.gate_failures(self.run_dir), [])

    def test_no_approval_fails_gate_but_passes_qc_floor(self):
        self.seeded(approved=False)
        self.assertEqual(db.validate(self.run_dir), [])
        self.assertTrue(any("no client approval" in f for f in db.gate_failures(self.run_dir)))

    def test_stub_board_never_validates(self):
        self.seeded(approved=False, provider="stub")
        self.assertTrue(any("stub placeholder" in f for f in db.validate(self.run_dir)))

    def test_approve_refuses_failing_board(self):
        self.seeded(approved=False)
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] = "nothing legible"
        db.save_record(self.run_dir, rec)
        with self.assertRaises(db.BoardError):
            db.approve(self.run_dir, "Client", "msg")

    def test_palette_must_be_the_resolved_client_palette(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["palette"][0]["hex"] = "#00FF00"
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("palette" in f for f in db.validate(self.run_dir)))

    def test_readback_hex_outside_palette_and_missing_hex(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] += "\nExtra #123456"
        rec["readback"]["text"] = rec["readback"]["text"].replace("#222222", "")
        db.save_record(self.run_dir, rec)
        fails = " | ".join(db.validate(self.run_dir))
        self.assertIn("#123456", fails)
        self.assertIn("#222222", fails)

    def test_required_block_absent_from_readback(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] = rec["readback"]["text"].replace("BUILT TO LAST.", "")
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("'footer'" in f for f in db.validate(self.run_dir)))

    def test_an_optional_block_that_is_on_the_board_must_be_legible_too(self):
        bf.make_run(self.run_dir, "checkout", {"icons": ["Plan", "Call"]})  # icons optional here
        bf.seed_board(self.run_dir, approved=False)
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] = rec["readback"]["text"].replace("Plan", "").replace("Call", "")
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("'icons'" in f for f in db.validate(self.run_dir)))

    def test_foreign_brand_text_on_board_fails(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] += "\nSET FOR LIFE"
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("another client" in f for f in db.validate(self.run_dir)))

    def test_logo_change_invalidates(self):
        self.seeded()
        bf.png(self.run_dir / "inputs" / "logo.png", (1, 2, 3))
        self.assertTrue(any("logo" in f for f in db.validate(self.run_dir)))

    def test_added_slot_makes_board_stale(self):
        self.seeded()
        bf.png(self.run_dir / "inputs" / "img9.png", (9, 9, 9))
        self.rewrite_request(lambda r: r["sections"][1]["slots"].append(
            {"slot_id": "IMG-009", "file": "inputs/img9.png"}))
        self.assertTrue(any("added" in f and "IMG-009" in f for f in db.gate_failures(self.run_dir)))

    def test_changed_image_file_fails(self):
        self.seeded()
        bf.png(self.run_dir / "inputs" / "img1.png", (9, 9, 9))
        self.assertTrue(any("IMG-001 changed" in f for f in db.validate(self.run_dir)))

    def test_replacing_a_supplied_image_after_approval_makes_it_stale(self):
        # probe 6: the supplied slot's file is pointed at a different image; the old file is untouched
        self.seeded(chain=True)
        self.assertEqual(db.gate_failures(self.run_dir), [])
        bf.png(self.run_dir / "inputs" / "replacement.png", (7, 7, 7))
        inv = self.run_dir / "desktop-wireframe" / "image-inventory.json"
        entries = json.loads(inv.read_text())
        entries[2]["file"] = "inputs/replacement.png"
        inv.write_text(json.dumps(entries))
        fails = " | ".join(db.gate_failures(self.run_dir))
        self.assertIn("IMG-003 changed", fails)
        self.assertIn("approved again", fails)

    def test_replacing_a_supplied_image_in_the_request_makes_it_stale(self):
        # probe 6, request route: the production request's supplied file is pointed elsewhere
        self.seeded(chain=True)
        self.rewrite_request(lambda r: r["sections"][1]["slots"][0].update(file="inputs/founder.png"))
        self.assertEqual(db.gate_failures(self.run_dir), [])  # same file as the inventory: no change
        bf.png(self.run_dir / "inputs" / "replacement.png", (7, 7, 7))
        self.rewrite_request(lambda r: r["sections"][1]["slots"][0].update(file="inputs/replacement.png"))
        fails = " | ".join(db.gate_failures(self.run_dir))
        self.assertIn("IMG-003", fails)
        self.assertIn("different supplied files", fails)

    def test_an_image_arriving_for_a_slot_after_approval_makes_it_stale(self):
        # probe 5: after approval the run's artifacts name a different real file for a slot
        self.seeded(chain=True)
        bf.png(self.run_dir / "image-generation-qc" / "Image-002-v2.png", (3, 3, 3))
        mp = self.run_dir / "image-map-upload" / "image-map.json"
        data = json.loads(mp.read_text())
        data["images"].append({"id": "IMG-002", "asset_file": "Image-002-v2.png"})
        mp.write_text(json.dumps(data))
        self.assertTrue(any("IMG-002 changed" in f for f in db.gate_failures(self.run_dir)))

    def test_a_vanished_image_fails_the_gate(self):
        self.seeded(chain=True)
        (self.run_dir / "image-generation-qc" / "Image-002.png").unlink()
        self.assertTrue(any("IMG-002" in f for f in db.gate_failures(self.run_dir)))

    def test_deleting_the_request_does_not_hide_a_change(self):
        self.seeded()
        (self.run_dir / "production-request.json").unlink()
        self.assertTrue(any("cannot be re-derived" in f for f in db.gate_failures(self.run_dir)))

    def test_changed_board_after_approval_is_stale(self):
        self.seeded()
        bf.png(self.run_dir / db.BOARD_FILE, (1, 1, 1))
        fails = " | ".join(db.gate_failures(self.run_dir))
        self.assertIn("changed after it was recorded", fails)

    def test_new_readback_clears_approval(self):
        self.seeded()
        db.finalize(self.run_dir, db.load_record(self.run_dir)["readback"]["text"], "again")
        self.assertIsNone(db.load_record(self.run_dir)["approval"])

    def test_wrong_page_role_for_run(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["page_role"] = "checkout"
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("run declares" in f for f in db.validate(self.run_dir)))


class ReadbackIsIndependentTests(Base):
    """The read-back is checked against the board image, never taken on the caller's word."""

    def make(self):
        bf.make_run(self.run_dir, "landing")
        request = self.request()
        plan = db.plan(self.run_dir, request)
        prompt, _ = db.compose_prompt(plan, request, self.run_dir)
        bf.render_board(self.run_dir / db.BOARD_FILE, plan["palette"])
        db.write_record(self.run_dir, plan, prompt,
                        {"provider": "kie", "mode": "active", "model": "m", "task_id": "t"}, 1)
        return "\n".join(bf.board_lines(plan))

    def test_a_transcript_that_is_just_the_contract_is_refused_when_the_board_shows_nothing(self):
        transcript = self.make()
        bf.BOARD_TEXT[0] = ""  # the board image is blank of text
        with self.assertRaises(db.BoardError) as cm:
            db.finalize(self.run_dir, transcript, "reader")
        self.assertIn("not supported by the board image", str(cm.exception))
        self.assertIsNone(db.load_record(self.run_dir)["readback"])

    def test_validate_re_reads_the_image_so_a_hand_edited_record_cannot_pass(self):
        transcript = self.make()
        bf.BOARD_TEXT[0] = transcript
        db.finalize(self.run_dir, transcript, "reader")
        self.assertEqual(db.validate(self.run_dir), [])
        bf.BOARD_TEXT[0] = "Test Client Co"  # the image shows far less than the record claims
        fails = " | ".join(db.validate(self.run_dir))
        self.assertIn("not supported by the board image", fails)
        self.assertIn("is not on the board image", fails)

    def test_one_block_missing_from_the_image_fails_even_when_the_rest_is_there(self):
        transcript = self.make()
        bf.BOARD_TEXT[0] = transcript.replace("BUILT TO LAST.", "").replace("WORK THAT COMPOUNDS.", "")
        db.finalize(self.run_dir, transcript, "reader")
        fails = db.validate(self.run_dir)
        self.assertTrue(any("block 'footer' is not on the board image" in f for f in fails), fails)

    def test_a_misread_hex_on_the_image_is_tolerated_but_a_stray_color_is_not(self):
        transcript = self.make()
        bf.BOARD_TEXT[0] = transcript.replace("#1F4E79", "#1F4E7B")  # one misread digit
        db.finalize(self.run_dir, transcript, "reader")
        self.assertEqual(db.validate(self.run_dir), [])
        bf.BOARD_TEXT[0] = transcript + "\n#00FF00"
        self.assertTrue(any("#00FF00" in f for f in db.validate(self.run_dir)))

    def test_the_palette_must_be_in_the_boards_pixels(self):
        transcript = self.make()
        bf.BOARD_TEXT[0] = transcript
        bf.png(self.run_dir / db.BOARD_FILE, (255, 255, 255), (1600, 1200))  # flat white board
        rec = db.load_record(self.run_dir)
        rec["board"]["sha256"] = db.sha256_file(self.run_dir / db.BOARD_FILE)
        db.save_record(self.run_dir, rec)
        db.finalize(self.run_dir, transcript, "reader")
        self.assertTrue(any("absent from the board's pixels" in f for f in db.validate(self.run_dir)))

    def test_a_readback_from_another_board_image_fails(self):
        transcript = self.make()
        bf.BOARD_TEXT[0] = transcript
        db.finalize(self.run_dir, transcript, "reader")
        rec = db.load_record(self.run_dir)
        rec["readback"]["board_sha256"] = "0" * 64
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("different board image" in f for f in db.validate(self.run_dir)))

    def test_finalize_refuses_a_board_that_changed_since_it_was_recorded(self):
        transcript = self.make()
        bf.BOARD_TEXT[0] = transcript
        bf.png(self.run_dir / db.BOARD_FILE, (1, 1, 1))
        with self.assertRaises(db.BoardError):
            db.finalize(self.run_dir, transcript, "reader")

    def test_no_reader_installed_fails_closed(self):
        transcript = self.make()
        with mock.patch.object(db, "ocr_text", side_effect=db.BoardError("tesseract is not installed")):
            with self.assertRaises(db.BoardError):
                db.finalize(self.run_dir, transcript, "reader")


@bf.needs_ocr
class RealReaderTests(Base):
    """The real tesseract on boards drawn with real text (no double)."""

    def setUp(self):
        super().setUp()
        mock.patch.stopall()  # use the real db.ocr_text

    def test_a_board_that_really_shows_its_text_passes(self):
        bf.make_run(self.run_dir, "landing", chain=True)
        bf.seed_real_board(self.run_dir)
        self.assertEqual(db.gate_failures(self.run_dir), [])

    def test_real_reader_finds_the_one_declared_text_the_image_lacks(self):
        bf.make_run(self.run_dir, "landing", {"side_taglines": ["BUILD STEADY", "BUILT FOR FOUNDERS"]})
        request = self.request()
        plan = db.plan(self.run_dir, request)
        prompt, _ = db.compose_prompt(plan, request, self.run_dir)
        lines = bf.board_lines(plan)
        bf.render_board(self.run_dir / db.BOARD_FILE, plan["palette"],
                        [x for x in lines if x != "BUILT FOR FOUNDERS"])
        db.write_record(self.run_dir, plan, prompt, {"provider": "kie", "mode": "a", "model": "m",
                                                     "task_id": "t"}, 1)
        db.finalize(self.run_dir, "\n".join(lines), "reader")  # the transcript claims every text
        fails = db.validate(self.run_dir)
        self.assertTrue(any("block 'side_taglines' is not on the board image" in f
                            and "BUILT FOR FOUNDERS" in f for f in fails), fails)

    def test_a_blank_board_with_a_contract_transcript_is_refused(self):
        bf.make_run(self.run_dir, "landing")
        request = self.request()
        plan = db.plan(self.run_dir, request)
        prompt, _ = db.compose_prompt(plan, request, self.run_dir)
        bf.render_board(self.run_dir / db.BOARD_FILE, plan["palette"])  # swatches, no words
        db.write_record(self.run_dir, plan, prompt, {"provider": "kie", "mode": "a", "model": "m",
                                                     "task_id": "t"}, 1)
        with self.assertRaises(db.BoardError) as cm:
            db.finalize(self.run_dir, "\n".join(bf.board_lines(plan)), "reader")
        self.assertIn("not supported by the board image", str(cm.exception))

    def test_cli_validate_and_gate_exit_codes(self):
        bf.make_run(self.run_dir, "landing")
        bf.seed_real_board(self.run_dir, approved=False)
        self.assertEqual(run([ROOT / "scripts" / "design_board.py", "validate", self.run_dir]).returncode, 0)
        self.assertEqual(run([ROOT / "scripts" / "design_board.py", "gate", self.run_dir]).returncode, 1)
        ok = run([ROOT / "scripts" / "design_board.py", "approve", self.run_dir,
                  "--by", "Test Client", "--evidence", "msg-1"])
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertEqual(run([ROOT / "scripts" / "design_board.py", "gate", self.run_dir]).returncode, 0)

    def test_cli_finalize_refuses_an_unsupported_transcript(self):
        bf.make_run(self.run_dir, "landing")
        request = self.request()
        plan = db.plan(self.run_dir, request)
        prompt, _ = db.compose_prompt(plan, request, self.run_dir)
        bf.render_board(self.run_dir / db.BOARD_FILE, plan["palette"])
        db.write_record(self.run_dir, plan, prompt, {"provider": "kie", "mode": "a", "model": "m",
                                                     "task_id": "t"}, 1)
        (self.run_dir / "rb.txt").write_text("\n".join(bf.board_lines(plan)), encoding="utf-8")
        out = run([ROOT / "scripts" / "design_board.py", "finalize", self.run_dir,
                   "--readback-file", self.run_dir / "rb.txt"])
        self.assertEqual(out.returncode, 1)
        self.assertIn("not supported by the board image", out.stdout)


class ExecutorTests(Base):
    def test_preflight_composes_board_for_landing_and_thank_you_without_a_call(self):
        for role in ("landing", "thank_you"):
            rd = bf.make_run(self.td / role, role)
            out = run([EXEC, rd, "--stages", "design-board", "--preflight"])
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn(f"PREFLIGHT design-board {role} ratio=4:3", out.stdout)
            self.assertIn("#1F4E79", out.stdout)
            self.assertFalse((rd / "design-board").exists(), "preflight writes nothing")

    def test_board_preflight_refuses_a_page_whose_images_are_not_made_yet(self):
        bf.make_run(self.run_dir, slot_files=1)
        out = run([EXEC, self.run_dir, "--stages", "design-board", "--preflight"])
        self.assertEqual(out.returncode, 1)
        self.assertIn("never art-direction stand-ins", out.stdout)

    def test_board_stage_runs_alone(self):
        bf.make_run(self.run_dir)
        out = run([EXEC, self.run_dir, "--stages", "design-board,final-mockups", "--preflight"])
        self.assertEqual(out.returncode, 1)
        self.assertIn("on its own", out.stdout)

    def test_stub_board_is_written_but_never_passes_the_gate(self):
        bf.make_run(self.run_dir)
        out = run([EXEC, self.run_dir, "--stages", "design-board", "--provider", "stub"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((self.run_dir / db.BOARD_FILE).is_file())
        self.assertTrue(any("stub placeholder" in f for f in db.validate(self.run_dir)))

    def test_stages_before_the_board_are_not_gated_by_it(self):
        # the board needs the page's images, which exist only after these stages and the image chain
        bf.make_run(self.run_dir)
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            out = run([EXEC, self.run_dir, "--stages", stage, "--preflight"])
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn(f"PREFLIGHT {stage}", out.stdout)

    def test_item_mode_is_not_gated_by_the_board(self):
        bf.make_run(self.run_dir)
        (self.run_dir / "image-inventory-prompts").mkdir()
        (self.run_dir / "image-inventory-prompts" / "IMG-001.txt").write_text("prompt")
        out = run([EXEC, self.run_dir, "--stage", "image-generation-qc", "--item", "IMG-001"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    @bf.needs_ocr
    def test_final_mockups_refused_without_approval_allowed_with_it(self):
        mock.patch.stopall()
        bf.make_run(self.run_dir, chain=True)
        refused = run([EXEC, self.run_dir, "--stages", "final-mockups", "--preflight"])
        self.assertEqual(refused.returncode, 1)
        self.assertIn("no board yet", refused.stdout)
        bf.seed_real_board(self.run_dir, approved=False)
        refused = run([EXEC, self.run_dir, "--stages", "final-mockups", "--preflight"])
        self.assertEqual(refused.returncode, 1)
        self.assertIn("no client approval recorded", refused.stdout)
        db.approve(self.run_dir, "Test Client", "msg-1")
        allowed = run([EXEC, self.run_dir, "--stages", "final-mockups", "--preflight"])
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertIn("PREFLIGHT final-mockups", allowed.stdout)
        # a later change to a real image revokes it
        bf.png(self.run_dir / "inputs" / "founder.png", (1, 1, 1))
        again = run([EXEC, self.run_dir, "--stages", "final-mockups", "--preflight"])
        self.assertEqual(again.returncode, 1)
        self.assertIn("IMG-003 changed", again.stdout)

    def test_a_multi_stage_run_that_includes_final_mockups_is_refused_before_any_call(self):
        bf.make_run(self.run_dir)
        out = run([EXEC, self.run_dir, "--stages", "desktop-wireframe,final-mockups"])
        self.assertEqual(out.returncode, 1)
        self.assertFalse((self.run_dir / "desktop-wireframe").exists())


class StageOrderTests(unittest.TestCase):
    """The board sits after image selection and gates the client-judged mockup onward."""

    def setUp(self):
        self.contract = json.loads((ROOT / "references" / "stage-contract.json").read_text())

    def test_board_is_after_the_image_chain_and_before_final_mockups(self):
        order = self.contract["stage_order"]
        board = order.index("design-board")
        for earlier in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "image-inventory-prompts",
                        "image-generation-qc", "image-map-upload"):
            self.assertLess(order.index(earlier), board, earlier)
        self.assertLess(board, order.index("final-mockups"))

    def test_dependencies(self):
        stages = self.contract["stages"]
        self.assertEqual(stages["design-board"]["depends_on"], ["image-map-upload"])
        self.assertIn("design-board", stages["final-mockups"]["depends_on"])
        for early in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "image-inventory-prompts",
                      "image-generation-qc", "image-map-upload"):
            self.assertNotIn("design-board", stages[early]["depends_on"], early)
        self.assertEqual(stages["design-board"]["approval_artifact"], "design-board/design-board.png")


class StageGateTests(Base):
    """The real design-board validator behind the real gate, on a three-stage fixture contract."""

    def setUp(self):
        super().setUp()
        mock.patch.stopall()  # the gate runs design_board.py as a subprocess: the real reader
        full = json.loads((ROOT / "references" / "stage-contract.json").read_text())
        keep = ["image-map-upload", "design-board", "final-mockups"]
        stages = {k: full["stages"][k] for k in keep}
        stages["image-map-upload"] = {"depends_on": [], "requires_artifacts": [],
                                      "artifacts": [{"glob": "image-map-upload/image-map.json", "min_count": 1}],
                                      "validators": ["gate:noop"], "review_required": False,
                                      "min_scores": None}
        stages["final-mockups"] = {"depends_on": ["image-map-upload", "design-board"],
                                   "requires_artifacts": [], "artifacts": [],
                                   "validators": ["gate:noop"], "review_required": False,
                                   "min_scores": None}
        contract = {"version": 1, "stage_order": keep, "stages": stages}
        self.contract = self.td / "contract.json"
        self.contract.write_text(json.dumps(contract), encoding="utf-8")
        self.env = {**bf.subprocess_env(), "STAGE_GATE_CONTRACT": str(self.contract)}
        bf.make_run(self.run_dir, chain=True)
        self.gate("init", self.run_dir)
        self.receipt("image-map-upload")
        self.assertEqual(self.gate("close", self.run_dir, "image-map-upload").returncode, 0)

    def gate(self, *args):
        return run([GATE, *args], env=self.env)

    def receipt(self, stage):
        path = self.run_dir / "private" / "receipts" / f"{stage}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "stage": stage, "status": "pass", "author_agent": "builder", "reviewer_agent": "reviewer",
            "started_at": "2026-10-19T10:00:00+00:00", "finished_at": "2026-10-19T10:30:00+00:00",
            "artifacts": [], "notes": "fixture"}), encoding="utf-8")

    def review(self):
        env = {k: v for k, v in self.env.items() if "SESSION" not in k}
        env["OPENCLAW_SESSION_ID"] = "reviewer-session"
        scores = json.dumps({"brand_fidelity": {"score": 9, "note": "Checked against the board bytes and the contract line by line."}})
        out = subprocess.run(
            [PY, str(WRITE_REVIEW), str(self.run_dir), "design-board", "design-board",
             "--scores", scores, "--verdict", "pass",
             "--performed-check", "Opened the board image and scored it against the contract.",
             "--next-current-artifact", "the stage receipt that closes on this review",
             "--author-session", "builder-session"], text=True, capture_output=True, env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    @bf.needs_ocr
    def test_final_mockups_is_refused_until_the_board_is_approved_and_closed(self):
        # 1. no board at all
        out = self.gate("check", self.run_dir, "final-mockups")
        self.assertEqual(out.returncode, 1)
        self.assertIn("dependency design-board is not closed", out.stdout + out.stderr)
        # 2. board made, read back, but the client has not approved: the board cannot close
        bf.seed_real_board(self.run_dir, approved=False)
        self.receipt("design-board")
        self.review()
        out = self.gate("close", self.run_dir, "design-board")
        self.assertEqual(out.returncode, 1)
        self.assertIn("no client approval recorded", out.stdout + out.stderr)
        self.assertEqual(self.gate("check", self.run_dir, "final-mockups").returncode, 1)
        # 3. client approval recorded: the board closes and final-mockups may start
        db.approve(self.run_dir, "Test Client", "msg-1")
        out = self.gate("close", self.run_dir, "design-board")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        out = self.gate("check", self.run_dir, "final-mockups")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # 4. any change to the approved board after close is caught by the closed-artifact hashes
        bf.png(self.run_dir / db.BOARD_FILE, (5, 5, 5))
        out = self.gate("check", self.run_dir, "final-mockups")
        self.assertEqual(out.returncode, 1)
        self.assertIn("changed after close", out.stdout + out.stderr)

    def test_brand_colors_unresolved_blocks_design_board_check(self):
        (self.run_dir / "inputs" / "brand.json").write_text(
            json.dumps({"brand_id": "test-client-co", "palette": {"gold": "CLIENT_MUST_SUPPLY"}}))
        out = self.gate("check", self.run_dir, "design-board")
        self.assertEqual(out.returncode, 1)
        self.assertIn("brand colors", out.stdout + out.stderr)


class EveryDeclaredTextIsOnTheImageTests(Base):
    """Round 2: the image is checked per declared text, never by a whole-block share. Each probe
    is a board whose image lacks one declared text while the transcript still claims it."""

    def seeded(self, extra=None, role="landing"):
        bf.make_run(self.run_dir, role, extra or {})
        bf.seed_board(self.run_dir, approved=False)
        self.assertEqual(db.validate(self.run_dir), [], "control: the full board passes")

    def drop(self, *lines, once=False):
        shown = bf.BOARD_TEXT[0].split("\n")
        for line in lines:
            shown.remove(line) if once else shown.__setitem__(slice(None), [x for x in shown if x != line])
        bf.BOARD_TEXT[0] = "\n".join(shown)

    def fails_for(self, block, text):
        fails = [f for f in db.validate(self.run_dir) if f"block {block!r} is not on the board image" in f]
        self.assertTrue(fails and text in fails[0], (block, text, db.validate(self.run_dir)))

    def test_one_of_two_side_taglines_missing_from_the_image_fails(self):
        self.seeded({"side_taglines": ["BUILD STEADY", "BUILT FOR FOUNDERS"]})
        self.drop("BUILT FOR FOUNDERS")
        self.fails_for("side_taglines", "BUILT FOR FOUNDERS")

    def test_one_of_two_text_tiles_missing_from_the_image_fails(self):
        self.seeded({"imagery_extras": [{"text": "WORK FIRST. REST AFTER."}, {"text": "SMALL STEPS COMPOUND."}]})
        self.drop("SMALL STEPS COMPOUND.")
        self.fails_for("imagery", "SMALL STEPS COMPOUND.")

    def test_two_of_five_cues_missing_from_the_image_fails(self):
        self.seeded()
        self.drop("Generous spacing", "No clutter")
        self.fails_for("cues", "Generous spacing")

    def test_a_gradient_caption_is_not_shown_by_a_longer_look_alike_word(self):
        # the banner line carries "growth"; the caption "ROOM TO GROW" must not pass on it
        self.seeded({"gradient": True, "gradient_caption": "ROOM TO GROW"})
        self.drop("ROOM TO GROW")
        self.fails_for("gradient", "ROOM TO GROW")

    def test_a_word_printed_once_cannot_show_two_texts(self):
        self.seeded({"side_taglines": ["BUILT TO LAST."]})  # the footer prints the same words
        self.drop("BUILT TO LAST.", once=True)
        self.fails_for("side_taglines", "BUILT TO LAST.")

    def test_one_misread_character_is_tolerated(self):
        self.seeded()
        bf.BOARD_TEXT[0] = bf.BOARD_TEXT[0].replace("Practical", "Practlcal").replace("honest", "honeet")
        self.assertEqual(db.validate(self.run_dir), [])

    def test_matching_rules(self):
        self.assertTrue(db.within_one("board", "bard") and db.within_one("plan", "plam"))
        self.assertFalse(db.within_one("grow", "growth") or db.within_one("abcde", "abxyz"))
        anchors = {"b": ["ROOM TO GROW", "Steady growth"]}
        self.assertEqual(db.image_misses(anchors, "room\nsteady growth"), {"b": ["ROOM TO GROW"]})
        self.assertEqual(db.image_misses(anchors, "room grow\nsteady growth"), {})
        # two machine reads: a word one read lacks may come from the other; counts are never summed
        self.assertEqual(db.image_misses({"b": ["room grow"]}, "room\fgrow\ngrowth"), {})
        self.assertEqual(db.image_misses({"b": ["plan plan"]}, "plan\fplan"), {"b": ["plan plan"]})


class ContractPartsAreImplementedTests(Base):
    """Round 2: the example board's aesthetic phrase line, banner second line and title line."""

    def test_aesthetic_is_five_or_six_words_with_a_phrase_line(self):
        for words in (3, 4, 7):
            rd = bf.make_run(self.td / f"w{words}", "landing",
                             {"aesthetic_words": [f"Word{n}x" for n in range(words)]})
            with self.assertRaises(db.BoardError) as cm:
                db.plan(rd, json.loads((rd / "production-request.json").read_text()))
            self.assertIn(f"five or six words, got {words}", str(cm.exception))
        for words in (5, 6):
            rd = bf.make_run(self.td / f"ok{words}", "landing",
                             {"aesthetic_words": [f"Word{n}x" for n in range(words)]})
            db.plan(rd, json.loads((rd / "production-request.json").read_text()))
        rd = bf.make_run(self.td / "nophrase", "landing", {"aesthetic_phrase": ""})
        with self.assertRaises(db.BoardError) as cm:
            db.plan(rd, json.loads((rd / "production-request.json").read_text()))
        self.assertIn("aesthetic_phrase", str(cm.exception))

    def test_aesthetic_is_optional_off_landing_but_whole_when_given(self):
        rd = bf.make_run(self.td / "none", "checkout", {"aesthetic_words": [], "aesthetic_phrase": ""})
        self.assertNotIn("aesthetic", [b["key"] for b in db.plan(
            rd, json.loads((rd / "production-request.json").read_text()))["blocks"] if b["present"]])
        rd = bf.make_run(self.td / "half", "checkout", {"aesthetic_phrase": ""})
        with self.assertRaises(db.BoardError):
            db.plan(rd, json.loads((rd / "production-request.json").read_text()))

    def test_phrase_line_and_title_line_reach_the_prompt_and_are_read_back(self):
        bf.make_run(self.run_dir, "landing", {"banner_subline": "Show up, then keep going."})
        plan = db.plan(self.run_dir, self.request())
        prompt, _ = db.compose_prompt(plan, self.request(), self.run_dir)
        for text in ("Plain steps and honest numbers", "Show up, then keep going.",
                     "Test Client Co — OFFICIAL VISUAL DIRECTION", "beside the logo"):
            self.assertIn(text, prompt)
        bf.seed_board(self.run_dir, approved=False)
        self.assertEqual(db.validate(self.run_dir), [])
        for block, text in (("aesthetic", "Plain steps and honest numbers"),
                            ("banner", "Show up, then keep going."),
                            ("header", "Test Client Co — OFFICIAL VISUAL DIRECTION")):
            self.assertIn(text, plan["expected"]["anchors"][block])
            bf.BOARD_TEXT[0] = "\n".join(bf.board_lines(plan))
            bf.BOARD_TEXT[0] = "\n".join(x for x in bf.BOARD_TEXT[0].split("\n") if x != text)
            self.assertTrue(any(f"block {block!r} is not on the board image" in f for f in db.validate(self.run_dir)), block)

    def test_banner_second_line_needs_the_banner_line(self):
        bf.make_run(self.run_dir, "checkout", {"banner_line": "", "banner_subline": "Second line."})
        with self.assertRaises(db.BoardError) as cm:
            db.plan(self.run_dir, self.request())
        self.assertIn("banner_line", str(cm.exception))

    def test_the_example_boards_phrase_line_is_not_another_clients_content(self):
        spec = {"brand_name": "Other Co"}
        self.assertTrue(db.foreign_hits("Soft luxury, modern wealth, lasting freedom", spec))


class BoardAttachesExactlyItsOwnPicturesTests(Base):
    """Round 2: the paid call sends the logo and the page's images and nothing else."""

    def make(self, refs=2):
        bf.make_run(self.run_dir, "landing", chain=True)
        for i in range(refs):
            bf.png(self.run_dir / "inputs" / f"style-ref-{i + 1}.png", (9, 9, 9 + i))
        self.rewrite_request(lambda r: r.update(
            {"references": [str(self.run_dir / "inputs" / f"style-ref-{i + 1}.png") for i in range(refs)],
             "input_extra": {"input_urls": ["/elsewhere/other-client.png"], "quality": "high"}}))

    def test_request_level_references_never_reach_the_board_call(self):
        import stage_executor as se
        self.make()
        plan, job = se.board_job(self.run_dir, self.request())
        sent = se.build_input(job, self.request())
        self.assertEqual(sent["input_urls"], job["references"])
        self.assertEqual(sent["quality"], "high")  # other request fields still pass through
        self.assertTrue(sent["input_urls"][0].endswith("inputs/logo.png"))
        self.assertEqual(len(sent["input_urls"]), 1 + len(plan["slots"]))
        self.assertIn(f"REFERENCES — {len(sent['input_urls'])} attached: the client logo first", job["prompt"])
        self.assertFalse(any("style-ref" in u or "other-client" in u for u in sent["input_urls"]))

    def test_the_preflight_count_and_the_record_equal_what_is_sent(self):
        import stage_executor as se
        self.make()
        out = run([EXEC, self.run_dir, "--stages", "design-board", "--preflight"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        plan, job = se.board_job(self.run_dir, self.request())
        self.assertIn(f"refs={len(se.build_input(job, self.request())['input_urls'])} ", out.stdout)
        bf.seed_board(self.run_dir, approved=False)
        rec = db.load_record(self.run_dir)
        self.assertEqual(rec["generation"]["references"], se.build_input(job, self.request())["input_urls"])

    def test_the_attachment_limit_holds_with_request_references(self):
        import stage_executor as se
        self.make(refs=4)
        def many(req):
            for i in range(1, 14):
                bf.png(self.run_dir / "inputs" / f"m{i}.png", (10 * i, 50, 90), (80, 60))
            req["sections"] = [{"section_id": "all", "section_name": "All", "copy": "x.",
                                "slots": [{"slot_id": f"IMG-{i:03d}", "file": f"inputs/m{i}.png"} for i in range(1, 14)]}]
        self.rewrite_request(many)
        (self.run_dir / "desktop-wireframe" / "image-inventory.json").unlink()
        _, job = se.board_job(self.run_dir, self.request())
        self.assertEqual(len(se.build_input(job, self.request())["input_urls"]), db.MAX_REFERENCES)

    def test_other_stages_still_attach_the_request_references(self):
        import stage_executor as se
        sent = se.build_input({"prompt": "p", "references": ["a.png"]}, {"references": ["r.png"]})
        self.assertEqual(sent["input_urls"], ["r.png", "a.png"])


if __name__ == "__main__":
    unittest.main()
