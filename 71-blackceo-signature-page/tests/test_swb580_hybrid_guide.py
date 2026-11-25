#!/usr/bin/env python3
"""SWB-580: the hybrid board's guide column (1.3.59).

The composer stacked the guide from the top with no tie to the mockup sections (drift of 190 to 320 px),
printed one identical type spec per section (Heading 72px and a CTA for every section) and drew the
wireframe annotations about 7 px tall. Now:
  * each guide block starts at its mockup section's own top (the desktop stitch receipt's y_offset scaled
    to the panel); validate_hybrid_board --check-board recomputes the tops from the stitch receipt and
    fails a block that sits off its section, a thumbnail drawn below half size, a receipt with no guide
    geometry, and a board whose pixels do not show the pinned thumbnail where the receipt says;
  * the per-section type specs come from the closed font map, only the elements the section has: the
    hero section prints the hero headline spec, the others the section heading spec, and a CTA spec only
    for a section the font map's `ctas` names; the validator refuses a section that prints another
    section's spec or a CTA it does not have; --refresh-record re-derives them with provenance;
  * the thumbnails stay the byte-pinned desktop-wireframe slices (contract H2), so no provenance check moved.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from PIL import Image  # noqa: E402

import build_hybrid_board as bhb  # noqa: E402
import validate_hybrid_board as vhb  # noqa: E402

IDS = ["1", "2", "3", "4", "5"]
PAGE_W = 100
HEIGHTS = [100, 50, 50, 50, 50]          # desktop section heights (panel px); the panel is 100 px wide
THUMB_COLORS = [(30, 180, 60), (240, 200, 30), (20, 20, 200), (200, 20, 200), (10, 200, 200)]
NAMES = ["Confirmation", "Order summary", "Access", "What happens next", "Help"]


def sha(path):
    return vhb.sha256(path)


def size(px, lh, tab_px, tab_lh):
    return {"desktop": {"px": px, "line_height": lh}, "tablet": {"px": tab_px, "line_height": tab_lh}}


FONT_MAP = {
    "fonts": {"display": "Playfair Display", "body": "Source Sans 3", "accent": "Source Sans 3"},
    "families": {"display": {"family": "Playfair Display"}, "body": {"family": "Source Sans 3"},
                 "accent": {"family": "Source Sans 3"}},
    "ctas": [{"section": "1", "label": "Go"}, {"section": "3", "label": "Open"}, {"section": "5", "label": "Contact"}],
    "typography": [
        {"element": "hero_headline", "role": "display", "serves": "Section 1 headline: HELLO",
         "sizes": size(72, 1.02, 56, 1.05)},
        {"element": "section_heading", "role": "display", "serves": "the h2 of each section",
         "sizes": size(44, 1.1, 36, 1.12)},
        {"element": "body", "role": "body", "serves": "every paragraph", "sizes": size(21, 1.6, 20, 1.6)},
        {"element": "cta_label", "role": "accent", "serves": "buttons", "sizes": size(19, 1.0, 18, 1.0),
         "style": "uppercase", "letter_spacing": "0.04em"},
    ],
}
HERO = "Playfair Display 72px / 1.02 desktop, 56px / 1.05 tablet"
H2 = "Playfair Display 44px / 1.1 desktop, 36px / 1.12 tablet"
BODY = "Source Sans 3 21px / 1.6 desktop, 20px / 1.6 tablet"
CTA = "Source Sans 3 19px / 1.0 desktop, 18px / 1.0 tablet, uppercase, tracking 0.04em"


def make_run(tmp, font_map=FONT_MAP):
    run = Path(tmp)
    fm, dw = run / "final-mockups", run / "desktop-wireframe"
    fm.mkdir(parents=True)
    dw.mkdir()
    total = sum(HEIGHTS)
    Image.new("RGB", (PAGE_W, total), (200, 40, 40)).save(fm / "mockup-full.png")
    Image.new("RGB", (40, 120), (40, 60, 220)).save(fm / "mockup-full-mobile.png")
    offsets, y = [], 0
    for h in HEIGHTS:
        offsets.append(y)
        y += h
    (fm / "stitch-receipt.json").write_text(json.dumps({
        "stitched_output": "mockup-full.png", "page_width": PAGE_W, "total_height": total,
        "sections": [{"order": i, "section_id": sid, "y_offset": off, "height": h, "width": PAGE_W}
                     for i, (sid, off, h) in enumerate(zip(IDS, offsets, HEIGHTS), start=1)]}), encoding="utf-8")
    # the wireframe slices: half the panel width, each as tall as its section, except the first, which is
    # shorter than its mockup section (so a stack from the top and a tie to the section differ)
    for i, (color, h) in enumerate(zip(THUMB_COLORS, [60] + HEIGHTS[1:]), start=1):
        Image.new("RGB", (50, h // 2), color).save(dw / f"section-{i:02d}.png")
    (dw / "section-plan.json").write_text(json.dumps([{"section_id": sid} for sid in IDS]), encoding="utf-8")
    (run / "font-action-plan").mkdir()
    (run / "font-action-plan" / "font-map.json").write_text(json.dumps(font_map), encoding="utf-8")
    derived = vhb.derive_type_specs(font_map, IDS) or {sid: {"heading": "H", "body": "B", "cta": "C"} for sid in IDS}
    record = {
        "board_output": "hybrid-board.png",
        "desktop_panel": {"source": "final-mockups/mockup-full.png", "sha256": sha(fm / "mockup-full.png")},
        "mobile_panel": {"source": "final-mockups/mockup-full-mobile.png",
                         "sha256": sha(fm / "mockup-full-mobile.png")},
        "guide": {"typography_source": "font-action-plan/font-map.json", "sections": [
            {"number": i, "section_id": sid, "name": name,
             "wireframe_thumbnail": f"desktop-wireframe/section-{i:02d}.png",
             "sha256": sha(dw / f"section-{i:02d}.png"), "type_specs": derived[sid]}
            for i, (sid, name) in enumerate(zip(IDS, NAMES), start=1)]},
    }
    (fm / "hybrid-board.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return run


def script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)], text=True, capture_output=True)


def compose(run):
    proc = script("build_hybrid_board.py", run, "--overwrite")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads((run / "final-mockups" / "hybrid-board-receipt.json").read_text())


def edit_receipt(run, fn):
    path = run / "final-mockups" / "hybrid-board-receipt.json"
    doc = json.loads(path.read_text())
    fn(doc)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def edit_record(run, fn):
    path = run / "final-mockups" / "hybrid-board.json"
    doc = json.loads(path.read_text())
    fn(doc)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = make_run(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_block_starts_at_its_mockup_section(self):
        receipt = compose(self.run_dir)
        scale = bhb.DESKTOP_W / PAGE_W
        top = receipt["panels"]["desktop"]["y"]
        offsets = [0, 100, 150, 200, 250]
        rows = receipt["guide"]["sections"]
        self.assertEqual([r["section_id"] for r in rows], IDS)
        for row, off in zip(rows, offsets):
            self.assertEqual(row["thumbnail"]["y"], top + round(off * scale), row)
            self.assertEqual(row["mockup_top"], row["thumbnail"]["y"])
        # the old stacking would have put section 2 right under section 1's 432 px thumbnail (720 px section)
        self.assertNotEqual(rows[1]["thumbnail"]["y"], top + rows[0]["thumbnail"]["height"] + 16)
        with Image.open(self.run_dir / "final-mockups" / "hybrid-board.png") as im:
            px = im.convert("RGB")
            gx = receipt["panels"]["guide"]["x"]
            for row, color in zip(rows, THUMB_COLORS):
                self.assertEqual(px.getpixel((gx + 3, row["thumbnail"]["y"] + 3)), color)
            # the gap under section 1's thumbnail (432 px tall, the section is 720 px) is blank
            self.assertEqual(px.getpixel((gx + 3, top + 500)), (255, 255, 255))
        self.assertEqual(script("validate_hybrid_board.py", self.run_dir, "--check-board").returncode, 0)

    def test_a_block_off_its_section_fails_by_name(self):
        compose(self.run_dir)
        edit_receipt(self.run_dir, lambda d: d["guide"]["sections"][1]["thumbnail"].update(
            y=d["guide"]["sections"][1]["thumbnail"]["y"] + 190))
        proc = script("validate_hybrid_board.py", self.run_dir, "--check-board")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("guide section 2: its block sits 190 px from the mockup section", proc.stdout)

    def test_the_tops_come_from_the_stitch_receipt_not_the_composers_own_receipt(self):
        compose(self.run_dir)
        # a composer receipt that lies about the mockup top does not help: the stitch receipt decides
        edit_receipt(self.run_dir, lambda d: d["guide"]["sections"][2].update(
            mockup_top=d["guide"]["sections"][2]["thumbnail"]["y"] + 300))
        self.assertEqual(script("validate_hybrid_board.py", self.run_dir, "--check-board").returncode, 0)
        stitch = self.run_dir / "final-mockups" / "stitch-receipt.json"
        doc = json.loads(stitch.read_text())
        doc["sections"][2]["y_offset"] += 40
        stitch.write_text(json.dumps(doc), encoding="utf-8")
        proc = script("validate_hybrid_board.py", self.run_dir, "--check-board")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("guide section 3: its block sits", proc.stdout)

    def test_a_board_with_no_guide_geometry_fails(self):
        compose(self.run_dir)
        edit_receipt(self.run_dir, lambda d: d.pop("guide"))
        proc = script("validate_hybrid_board.py", self.run_dir, "--check-board")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("no guide geometry", proc.stdout)

    def test_the_composer_refuses_without_a_stitch_receipt_and_writes_nothing(self):
        (self.run_dir / "final-mockups" / "stitch-receipt.json").unlink()
        proc = script("build_hybrid_board.py", self.run_dir)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("cannot align the guide", proc.stdout)
        self.assertFalse((self.run_dir / "final-mockups" / "hybrid-board.png").exists())


class ReadabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = make_run(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_thumbnails_are_drawn_at_no_less_than_half_size_and_the_specs_at_a_readable_size(self):
        # the 1440 px wireframe page at the guide's thumbnail width: its ~25 px annotations stay >= 12 px
        self.assertGreaterEqual(bhb.THUMB_W / 1440, 0.5)
        self.assertGreaterEqual(bhb.SPEC_FONT, 14)
        self.assertGreaterEqual(bhb.NAME_FONT, bhb.SPEC_FONT)
        receipt = compose(self.run_dir)
        for row in receipt["guide"]["sections"]:
            self.assertGreaterEqual(row["thumbnail_scale"], vhb.MIN_THUMB_SCALE)
            self.assertEqual(row["thumbnail"]["width"], bhb.THUMB_W)

    def test_a_thumbnail_drawn_too_small_fails_by_name(self):
        compose(self.run_dir)
        edit_receipt(self.run_dir, lambda d: d["guide"]["sections"][0].update(thumbnail_scale=0.278))
        proc = script("validate_hybrid_board.py", self.run_dir, "--check-board")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("unreadable at that size", proc.stdout)

    def test_the_board_must_show_the_pinned_thumbnail_where_the_receipt_says(self):
        receipt = compose(self.run_dir)
        board = self.run_dir / "final-mockups" / "hybrid-board.png"
        row = receipt["guide"]["sections"][3]["thumbnail"]
        with Image.open(board) as im:
            sheet = im.convert("RGB")
        sheet.paste((0, 0, 0), (row["x"], row["y"], row["x"] + row["width"], row["y"] + row["height"]))
        sheet.save(board)
        edit_receipt(self.run_dir, lambda d: d.update(output_sha256=vhb.sha256(board)))
        proc = script("validate_hybrid_board.py", self.run_dir, "--check-board")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("guide section 4: the board does not show the pinned wireframe thumbnail", proc.stdout)

    def test_the_thumbnails_stay_the_byte_pinned_wireframe_slices(self):
        compose(self.run_dir)
        Image.new("RGB", (50, 25), (9, 9, 9)).save(self.run_dir / "desktop-wireframe" / "section-02.png")
        proc = script("validate_hybrid_board.py", self.run_dir, "--check-board")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("does not hash to the recorded sha256", proc.stdout)
        edit_record(self.run_dir, lambda d: d["guide"]["sections"][1].update(
            wireframe_thumbnail="final-mockups/mockup-full.png"))
        proc = script("validate_hybrid_board.py", self.run_dir)
        self.assertIn("must be the section's desktop wireframe slice under desktop-wireframe/", proc.stdout)


class TypeSpecTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = make_run(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def validate(self, *extra):
        return script("validate_hybrid_board.py", self.run_dir, *extra)

    def specs(self):
        doc = json.loads((self.run_dir / "final-mockups" / "hybrid-board.json").read_text())
        return {s["section_id"]: s["type_specs"] for s in doc["guide"]["sections"]}

    def test_each_section_gets_only_the_elements_it_has(self):
        got = self.specs()
        self.assertEqual(got["1"], {"heading": HERO, "body": BODY, "cta": CTA})
        self.assertEqual(got["2"], {"heading": H2, "body": BODY})
        self.assertEqual(got["3"], {"heading": H2, "body": BODY, "cta": CTA})
        self.assertEqual(got["4"], {"heading": H2, "body": BODY})
        self.assertEqual(got["5"], {"heading": H2, "body": BODY, "cta": CTA})
        self.assertEqual(self.validate().returncode, 0)

    def test_a_cta_spec_on_a_section_with_no_button_fails_by_name(self):
        edit_record(self.run_dir, lambda d: d["guide"]["sections"][1]["type_specs"].update(cta=CTA))
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("guide section 2: type_specs.cta is printed", proc.stdout)

    def test_a_missing_cta_on_a_section_with_a_button_fails(self):
        edit_record(self.run_dir, lambda d: d["guide"]["sections"][2]["type_specs"].pop("cta"))
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("type_specs.cta", proc.stdout)

    def test_the_hero_spec_on_an_inner_section_fails_by_name(self):
        edit_record(self.run_dir, lambda d: d["guide"]["sections"][1]["type_specs"].update(heading=HERO))
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("guide section 2: type_specs.heading", proc.stdout)
        self.assertIn(H2, proc.stdout)

    def test_the_old_identical_specs_for_every_section_fail(self):
        def same(d):
            for s in d["guide"]["sections"]:
                s["type_specs"] = {"heading": HERO, "body": BODY, "cta": CTA}
        edit_record(self.run_dir, same)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("guide section 2", proc.stdout)
        self.assertIn("guide section 4", proc.stdout)

    def test_a_font_map_without_typography_is_checked_structurally_as_before(self):
        run = make_run(tempfile.mkdtemp(dir=self.tmp.name), font_map={})
        proc = script("validate_hybrid_board.py", run)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        edit_record(run, lambda d: d["guide"]["sections"][0]["type_specs"].pop("cta"))
        self.assertIn("type_specs.cta", script("validate_hybrid_board.py", run).stdout)

    def test_the_board_prints_no_cta_line_for_a_section_without_one(self):
        # the lines the composer draws for section 2 come from its record: no CTA entry, so no CTA line
        text = []
        real = bhb._wrap_px

        def spy(draw, t, font, w):
            text.append(t)
            return real(draw, t, font, w)
        bhb._wrap_px = spy
        try:
            run_dir = self.run_dir
            rc = bhb.compose_board(run_dir, json.loads((run_dir / "final-mockups" / "hybrid-board.json").read_text()), True)
        finally:
            bhb._wrap_px = real
        self.assertEqual(rc, 0)
        self.assertEqual(sum(t.startswith("CTA:") for t in text), 3)
        self.assertEqual(sum(t.startswith("Heading: Playfair Display 72px") for t in text), 1)
        self.assertEqual(sum(t.startswith("Heading: Playfair Display 44px") for t in text), 4)

    def test_refresh_rederives_the_specs_from_the_font_map_with_provenance(self):
        guide = json.loads((self.run_dir / "final-mockups" / "hybrid-board.json").read_text())["guide"]
        for s in guide["sections"]:
            s["type_specs"] = {"heading": HERO, "body": BODY, "cta": CTA}      # the old, identical specs
        block = bhb._rederive_type_specs(self.run_dir, guide)
        self.assertEqual({s["section_id"]: s["type_specs"] for s in guide["sections"]}, {
            "1": {"heading": HERO, "body": BODY, "cta": CTA}, "2": {"heading": H2, "body": BODY},
            "3": {"heading": H2, "body": BODY, "cta": CTA}, "4": {"heading": H2, "body": BODY},
            "5": {"heading": H2, "body": BODY, "cta": CTA}})
        self.assertEqual(block["source"], "font-action-plan/font-map.json")
        self.assertEqual(block["source_sha256"], sha(self.run_dir / "font-action-plan" / "font-map.json"))
        self.assertEqual(block["prior"]["2"], {"heading": HERO, "body": BODY, "cta": CTA})
        self.assertEqual(block["new"]["2"], {"heading": H2, "body": BODY})

    def test_refresh_leaves_a_guide_alone_when_the_font_map_has_no_typography(self):
        run = make_run(tempfile.mkdtemp(dir=self.tmp.name), font_map={})
        guide = json.loads((run / "final-mockups" / "hybrid-board.json").read_text())["guide"]
        before = json.dumps(guide, sort_keys=True)
        self.assertIsNone(bhb._rederive_type_specs(run, guide))
        self.assertEqual(json.dumps(guide, sort_keys=True), before)

    def test_edited_specs_after_a_refresh_fail_the_provenance_check(self):
        rec_path = self.run_dir / "final-mockups" / "hybrid-board.json"
        rec = json.loads(rec_path.read_text())
        block = {"tool": "build_hybrid_board.py --refresh-record", "refreshed_at": "2026-11-24T00:00:00+00:00",
                 "prior": {"desktop_panel": None, "mobile_panel": None},
                 "new": {"desktop_panel": rec["desktop_panel"], "mobile_panel": rec["mobile_panel"]},
                 "guide_type_specs": {"source": "font-action-plan/font-map.json", "source_sha256": "0" * 64,
                                      "prior": {}, "new": {s["section_id"]: json.loads(json.dumps(s["type_specs"]))
                                                           for s in rec["guide"]["sections"]}}}
        block["receipt_sha256"] = bhb._provenance_hash(block)
        rec["refreshed_from"] = block
        rec_path.write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(self.validate().returncode, 0)
        # edit a spec and re-seal nothing: the block no longer matches
        rec["guide"]["sections"][0]["type_specs"]["body"] = "Source Sans 3 21px / 1.6 desktop, 20px / 1.6 tablet "
        rec_path.write_text(json.dumps(rec), encoding="utf-8")
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("type_specs differ from refreshed_from.guide_type_specs.new", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
