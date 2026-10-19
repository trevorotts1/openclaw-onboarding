#!/usr/bin/env python3
"""Every image stage also delivers a combined overview board (second view next
to the long PDF): scripts/build_overview_board.py, references/overview-board.md."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_overview_board as bob  # noqa: E402

spec = importlib.util.spec_from_file_location("stage_executor", SCRIPTS / "stage_executor.py")
exe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exe)

COLORS = [(200, 30, 30), (30, 160, 40), (30, 50, 210), (230, 200, 20)]
BRAND = {"brand_id": "Test Co", "palette": {"a": "#FAF9F5", "b": "#162F23", "c": "#A64335"}}


def make_run(tmp, stage="final-mockups", n=4, drop=None):
    from PIL import Image
    run = Path(tmp)
    for device, w, h, tpl in (("desktop", 1440, 1000, "desktop/part-{n:02d}.png"),
                              ("mobile", 390, 520, "mobile/part-{n:02d}.png")):
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
                             ["final-mockups-desktop-overview.png", "final-mockups-mobile-overview.png"])
            for p, size in built:
                with Image.open(p) as im:
                    self.assertEqual(im.size, size)
            receipt = json.loads((out / "final-mockups-mobile-overview.json").read_text())
            self.assertEqual([f["label"] for f in receipt["geometry"]["frames"]],
                             ["SECTIONS 1-2", "SECTIONS 3-4"])
            self.assertEqual(receipt["sections"][0]["name"], "Name 1")

    def test_desktop_sections_scaled_uniformly_top_to_bottom(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(tmp)
            p, _ = build(run, device="desktop")[0]
            im = Image.open(p).convert("RGB")
            geo = json.loads((run / "review-pdfs/final-mockups-desktop-overview.json").read_text())["geometry"]
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
            self.assertTrue((run / "review-pdfs/final-mockups-mobile-overview.png").is_file())


if __name__ == "__main__":
    unittest.main()
