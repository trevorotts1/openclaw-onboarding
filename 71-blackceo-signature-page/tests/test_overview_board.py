#!/usr/bin/env python3
"""Every image stage also delivers a combined overview board (second view next
to the long PDF): scripts/build_overview_board.py, references/overview-board.md."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_overview_board as bob  # noqa: E402
from brand_fixture import give_blackceo_colors  # noqa: E402

spec = importlib.util.spec_from_file_location("stage_executor", SCRIPTS / "stage_executor.py")
exe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe)

COLORS = [(200, 30, 30), (30, 160, 40), (30, 50, 210), (230, 200, 20)]
BRAND = {"brand_id": "Test Co", "palette": {"a": "#FAF9F5", "b": "#162F23", "c": "#A64335"}}


def make_run(tmp, stage="final-mockups", n=4, drop=None, mh=520):
    from PIL import Image
    run = Path(tmp)
    for device, w, h, tpl in (("desktop", 1440, 1000, "desktop/part-{n:02d}.png"),
                              ("mobile", 390, mh, "mobile/part-{n:02d}.png")):
        for i in range(1, n + 1):
            if i == drop:
                continue
            path = run / stage / tpl.format(n=i)
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (w, h), COLORS[i - 1]).save(path)
    (run / "production-request.json").write_text(json.dumps({"sections": [
        {"section_id": f"S0{i}", "section_name": f"Name {i}", "cta": "GO NOW" if i == 1 else None}
        for i in range(1, n + 1)]}), encoding="utf-8")
    (run / "brand.json").write_text(json.dumps(BRAND), encoding="utf-8")
    give_blackceo_colors(run)  # the executor hook resolves the run's brand colors, as every image stage does
    return run


def build(run, stage="final-mockups", **kw):
    return bob.build_stage(run, stage, brand=run / "brand.json", **kw)


class OverviewBoardTests(unittest.TestCase):
    def test_both_boards_named_and_receipted(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            built = build(run)
            out = run / "review-pdfs"
            self.assertEqual([p.name for p, _ in built],
                             ["landing_DESKTOP_MOCKUP-FINAL-BOARD.png", "landing_MOBILE_MOCKUP-FINAL-BOARD.png",
                              "landing_DESKTOP-and-MOBILE_MOCKUP-FINAL-BOARD.png"])
            for p, size in built:
                with Image.open(p) as im:
                    self.assertEqual(im.size, size)
            receipt = json.loads((out / "landing_MOBILE_MOCKUP-FINAL-BOARD.json").read_text())
            self.assertEqual([f["label"] for f in receipt["geometry"]["frames"]],
                             ["SECTIONS 1-2", "SECTIONS 3-4"])
            self.assertEqual(receipt["sections"][0]["name"], "Name 1")

    def test_combined_board_named_receipted_and_pinned_to_both_devices(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            built = build(run, device="combined")
            self.assertEqual([p.name for p, _ in built], ["landing_DESKTOP-and-MOBILE_MOCKUP-FINAL-BOARD.png"])
            p, size = built[0]
            with Image.open(p) as im:
                self.assertEqual(im.size, size)
            r = json.loads((run / "review-pdfs/landing_DESKTOP-and-MOBILE_MOCKUP-FINAL-BOARD.json").read_text())
            self.assertEqual((r["device"], r["board"], r["stage"]), ("combined", p.name, "final-mockups"))
            self.assertEqual(r["output_sha256"], bob.sha256(p))
            first = r["sections"][0]["images"]
            self.assertEqual([i["device"] for i in first], ["desktop", "mobile"])
            self.assertEqual(first[1]["image"], "final-mockups/mobile/part-01.png")
            self.assertEqual(first[1]["sha256"], bob.sha256(run / "final-mockups/mobile/part-01.png"))
            self.assertEqual(r["geometry"]["layout"], "combined")

    def test_combined_board_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            p, _ = build(run, device="combined")[0]
            first = (bob.sha256(p), (run / "review-pdfs/landing_DESKTOP-and-MOBILE_MOCKUP-FINAL-BOARD.json").read_text())
            p, _ = build(run, device="combined")[0]
            self.assertEqual(first, (bob.sha256(p), (run / "review-pdfs/landing_DESKTOP-and-MOBILE_MOCKUP-FINAL-BOARD.json").read_text()))

    def test_combined_keeps_section_order_across_desktop_column_and_mobile_parts(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp, n=4, mh=1000)
            p, _ = build(run, device="combined")[0]
            im = Image.open(p).convert("RGB")
            geo = json.loads((run / "review-pdfs/landing_DESKTOP-and-MOBILE_MOCKUP-FINAL-BOARD.json").read_text())["geometry"]
            ids = [f"S0{i}" for i in range(1, 5)]
            self.assertEqual([s["id"] for s in geo["sections"]], ids)
            self.assertEqual([i for part in geo["mobile_parts"] for i in part["sections"]], ids)
            self.assertGreater(len(geo["mobile_parts"]), 1)
            ys = [s["page_y"] for s in geo["sections"]]
            self.assertEqual(ys, sorted(ys))
            for sec, color in zip(geo["sections"], COLORS):  # desktop column: section i is the i-th color
                self.assertEqual(im.getpixel((geo["page_x"] + 10, sec["page_y"] + 5)), color)
            seen = []
            for part in geo["mobile_parts"]:  # mobile parts: sections in order, top to bottom, left to right
                self.assertEqual(part["section_y"], sorted(part["section_y"]))
                for sid, y in zip(part["sections"], part["section_y"]):
                    color = COLORS[ids.index(sid)]
                    self.assertEqual(im.getpixel((part["x"] + 10, y + 5)), color)
                    seen.append(sid)
            self.assertEqual(seen, ids)

    def test_split_parts_cuts_only_between_sections_and_balances(self):
        self.assertEqual(bob.split_parts([1, 1, 1, 1, 1, 1], 3), [[0, 1], [2, 3], [4, 5]])
        self.assertEqual(bob.split_parts([5, 1, 1, 1, 1, 1], 3), [[0], [1, 2, 3, 4], [5]])
        self.assertEqual(bob.split_parts([3, 2], 3), [[0], [1]])
        flat = [i for part in bob.split_parts([2, 7, 1, 1, 4, 3, 3], 3) for i in part]
        self.assertEqual(flat, list(range(7)))

    def test_combined_fails_closed_on_count_mismatch_and_removes_stale_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            built = build(run)
            combined = built[2][0]
            self.assertTrue(combined.is_file())
            (run / "final-mockups/mobile/part-04.png").unlink()
            with self.assertRaises(bob.BoardError):
                build(run, device="combined")
            self.assertFalse(combined.exists())
            self.assertFalse(combined.with_suffix(".json").exists())

    def test_wireframe_pair_combines_once_both_stages_delivered(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "production-request.json").write_text(json.dumps({"sections": [
                {"section_id": f"S0{i}", "section_name": f"Name {i}"} for i in (1, 2)]}), encoding="utf-8")
            (run / "brand.json").write_text(json.dumps(BRAND), encoding="utf-8")
            for i in (1, 2):
                path = run / "desktop-wireframe" / f"section-{i:02d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (1440, 810), COLORS[i - 1]).save(path)
            first = bob.build_stage(run, "desktop-wireframe", brand=run / "brand.json")  # mobile stage not run yet
            self.assertEqual([p.name for p, _ in first], ["landing_DESKTOP_WIREFRAME-BOARD.png"])
            mobile = run / "mobile-tablet"
            mobile.mkdir()
            Image.new("RGB", (390, 900), COLORS[0]).save(mobile / "section-01.png")
            half = bob.build_stage(run, "desktop-wireframe", brand=run / "brand.json")  # half-delivered sibling: skip
            self.assertEqual([p.name for p, _ in half], ["landing_DESKTOP_WIREFRAME-BOARD.png"])
            Image.new("RGB", (390, 900), COLORS[1]).save(mobile / "section-02.png")
            built = bob.build_stage(run, "mobile-tablet", brand=run / "brand.json")
            self.assertEqual([p.name for p, _ in built],
                             ["landing_MOBILE_WIREFRAME-BOARD.png", "landing_DESKTOP-and-MOBILE_WIREFRAME-BOARD.png"])

    def test_wireframe_combined_skipped_until_sibling_stage_has_images(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "production-request.json").write_text(json.dumps({"sections": [
                {"section_id": "S01", "section_name": "Name 1"}]}), encoding="utf-8")
            (run / "brand.json").write_text(json.dumps(BRAND), encoding="utf-8")
            path = run / "desktop-wireframe/section-01.png"
            path.parent.mkdir(parents=True)
            Image.new("RGB", (1440, 810), COLORS[0]).save(path)
            built = bob.build_stage(run, "desktop-wireframe", brand=run / "brand.json")
            self.assertEqual([p.name for p, _ in built], ["landing_DESKTOP_WIREFRAME-BOARD.png"])
            with self.assertRaises(bob.BoardError):  # asked for explicitly, it must fail, not skip
                bob.build_stage(run, "desktop-wireframe", device="combined", brand=run / "brand.json")

    def test_wireframe_partial_or_stale_sibling_never_costs_the_desktop_board(self):
        from PIL import Image

        class Provider:
            name = "kie"
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "production-request.json").write_text(json.dumps({"sections": [
                {"section_id": f"S0{i}", "section_name": f"Name {i}"} for i in (1, 2, 3)]}), encoding="utf-8")
            (run / "brand.json").write_text(json.dumps(BRAND), encoding="utf-8")
            give_blackceo_colors(run)
            for stage, w, h in (("desktop-wireframe", 1440, 810), ("mobile-tablet", 390, 900)):
                for i in (1, 2, 3):
                    path = run / stage / f"section-{i:02d}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (w, h), COLORS[i - 1]).save(path)
            out = run / "review-pdfs"
            both = bob.build_stage(run, "desktop-wireframe", brand=run / "brand.json")
            self.assertEqual(len(both), 2)
            combined = out / "landing_DESKTOP-and-MOBILE_WIREFRAME-BOARD.png"
            self.assertTrue(combined.is_file())
            (run / "mobile-tablet/section-03.png").unlink()  # interrupted run: 2 of 3
            done = exe.overview_boards("desktop-wireframe", run, Provider(), "production-request.json", 3)
            self.assertEqual(done["status"], "pass", done["output"])
            self.assertTrue((out / "landing_DESKTOP_WIREFRAME-BOARD.png").is_file())
            self.assertFalse(combined.exists())  # stale combined board removed on the skip
            self.assertFalse(combined.with_suffix(".json").exists())
            Image.new("RGB", (390, 900), COLORS[0]).save(run / "mobile-tablet/section-03.png")
            Image.new("RGB", (390, 900), COLORS[0]).save(run / "mobile-tablet/section-04.png")
            with self.assertRaises(bob.BoardError):  # sibling holds more images than sections: real mismatch
                bob.build_stage(run, "desktop-wireframe", brand=run / "brand.json")
            (run / "mobile-tablet/section-04.png").unlink()
            shutil.rmtree(run / "mobile-tablet")  # empty sibling with a stale combined board present
            (out / "landing_DESKTOP-and-MOBILE_WIREFRAME-BOARD.png").write_bytes(b"old")
            (out / "landing_DESKTOP-and-MOBILE_WIREFRAME-BOARD.json").write_text("{}")
            bob.build_stage(run, "desktop-wireframe", brand=run / "brand.json")
            self.assertFalse((out / "landing_DESKTOP-and-MOBILE_WIREFRAME-BOARD.png").exists())
            self.assertFalse((out / "landing_DESKTOP-and-MOBILE_WIREFRAME-BOARD.json").exists())

    def test_mobile_note_never_covers_subtitle_with_short_title(self):
        # 3 frames + the brand-id title (shorter than the subtitle) was the overlap case
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp, n=3, mh=1000)
            for stage_title in ("BLACKCEO", "X"):
                p, (w, _h) = bob.build_stage(run, "final-mockups", device="mobile", title=stage_title,
                                             brand=run / "brand.json")[0]
                geo = json.loads((run / "review-pdfs/landing_MOBILE_MOCKUP-FINAL-BOARD.json").read_text())["geometry"]
                self.assertEqual(len(geo["frames"]), 3)
                sub = bob.font("bold", 24).getlength(f"MOBILE {bob.STAGE_LABEL['final-mockups']} (COMPLETE SCROLL)")
                note = max(bob.font("sans", 20).getlength(n) for n in (
                    f"Optimized for mobile ({bob.VIEWPORT_RANGE})",
                    "Same content and flow as desktop \u00b7 No section labels on the page")) + 48
                self.assertGreaterEqual(w, bob.D_MARGIN + sub + 40 + note + bob.D_MARGIN, stage_title)

    def test_desktop_sections_scaled_uniformly_top_to_bottom(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            p, _ = build(run, device="desktop")[0]
            im = Image.open(p).convert("RGB")
            geo = json.loads((run / "review-pdfs/landing_DESKTOP_MOCKUP-FINAL-BOARD.json").read_text())["geometry"]
            col_h = round(1000 * bob.D_PAGE_W / 1440)
            for sec, color in zip(geo["sections"], COLORS):
                y = sec["page_y"]
                self.assertEqual(im.getpixel((bob.D_MARGIN + 10, y + 5)), color)
                self.assertEqual(im.getpixel((bob.D_MARGIN + bob.D_PAGE_W - 5, y + col_h - 5)), color)

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            first = [bob.sha256(p) for p, _ in build(run)]
            self.assertEqual(first, [bob.sha256(p) for p, _ in build(run)])

    def test_missing_section_fails_closed_and_removes_stale_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            built = build(run)
            (run / "final-mockups/desktop/part-03.png").unlink()
            with self.assertRaises(bob.BoardError) as ctx:
                build(run)
            self.assertIn("03", str(ctx.exception))
            self.assertFalse(built[0][0].exists())

    def test_trailing_section_missing_fails_against_request_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp, drop=4)
            req = json.loads((run / "production-request.json").read_text())
            self.assertEqual(len(req["sections"]), 4)
            with self.assertRaises(bob.BoardError):
                build(run)

    def test_no_section_names_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            (run / "production-request.json").unlink()
            with self.assertRaises(bob.BoardError):
                build(run)

    def test_grouping_is_greedy_and_never_splits(self):
        self.assertEqual(bob.group_sections([400, 400, 400, 400], 840), [[0, 1], [2, 3]])
        self.assertEqual(bob.group_sections([900, 300, 300], 840), [[0], [1, 2]])

    def test_skill_standard_type_sizes_are_starred_recorded_ones_are_not(self):
        lines, star = bob.spec_lines({"name": "x"}, "mobile", (390, 520))
        self.assertTrue(star)
        self.assertIn("Headline: 34–48px*", lines)
        lines, star = bob.spec_lines({"type_specs": {"h1": "60px", "h2": "50px", "body": "19px", "cta": "18px"},
                                      "slot_ratios": [("IMG-001", "3:2")]}, "desktop", (1440, 1920))
        self.assertFalse(star)
        self.assertIn("Headline: H1 60px · H2 50px", lines)
        self.assertIn("Image: 3:2 (IMG-001)", lines)
        self.assertIn("Frame: 3:4 · 1440×1920px", lines)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            cmd = [sys.executable, str(SCRIPTS / "build_overview_board.py"), str(run),
                   "--stage", "final-mockups", "--brand", str(run / "brand.json")]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            (run / "final-mockups/mobile/part-02.png").unlink()
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("FAIL:", proc.stdout)

    def test_executor_hook_runs_for_kie_and_skips_stub(self):
        class Provider:
            def __init__(self, name):
                self.name = name
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            skipped = exe.overview_boards("final-mockups", run, Provider("stub"), "production-request.json")
            self.assertEqual(skipped["status"], "skipped")
            done = exe.overview_boards("final-mockups", run, Provider("kie"), "production-request.json", 4)
            self.assertEqual(done["status"], "pass", done["output"])
            self.assertTrue((run / "review-pdfs/landing_MOBILE_MOCKUP-FINAL-BOARD.png").is_file())
            self.assertTrue((run / "review-pdfs/landing_DESKTOP-and-MOBILE_MOCKUP-FINAL-BOARD.png").is_file())


if __name__ == "__main__":
    unittest.main()
