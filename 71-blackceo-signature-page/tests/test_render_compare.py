#!/usr/bin/env python3
"""Tests for render_page.py and compare_sheet.py.

Mockup-mode fixtures (no browser needed):
  - compare_sheet missing-side -> exit 1
  - compare_sheet stitching / label-bar / piece-height logic (unit tests on
    Pillow images)

Playwright path (render_page.py) runs only when Playwright + Chromium are
available; otherwise those tests are skipped, not failed.
"""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PY = sys.executable

_spec = importlib.util.spec_from_file_location("compare_sheet", SCRIPTS / "compare_sheet.py")
compare_sheet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_sheet)

_spec_r = importlib.util.spec_from_file_location("render_page", SCRIPTS / "render_page.py")
render_page = importlib.util.module_from_spec(_spec_r)
_spec_r.loader.exec_module(render_page)

try:
    from PIL import Image
except ImportError:
    raise SystemExit("Pillow is required for these tests")

try:
    from playwright.sync_api import sync_playwright

    _probe_dir = tempfile.mkdtemp(prefix="skill71-probe-")
    try:
        with sync_playwright() as p:
            # launch_persistent_context (NOT a bare launch()) — headless, D6-safe
            # (guard-agent-browser-managed section 5).
            _probe = p.chromium.launch_persistent_context(_probe_dir, headless=True)
            _probe.close()
    finally:
        shutil.rmtree(_probe_dir, ignore_errors=True)
    PLAYWRIGHT_OK = True
except Exception:
    PLAYWRIGHT_OK = False


def run(args, expect=None):
    proc = subprocess.run(
        [PY] + [str(a) for a in args], text=True, capture_output=True
    )
    if expect is not None and proc.returncode != expect:
        raise AssertionError(
            f"expected exit {expect}, got {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def make_run_dir(base, with_desktop=True, with_mobile=True, with_pages=True):
    run_dir = base / "run"
    (run_dir / "final-mockups" / "desktop").mkdir(parents=True, exist_ok=True)
    (run_dir / "final-mockups" / "mobile").mkdir(parents=True, exist_ok=True)
    if with_desktop:
        Image.new("RGB", (1440, 1600), (26, 26, 46)).save(
            run_dir / "final-mockups" / "desktop" / "part-01.png"
        )
        Image.new("RGB", (1440, 1200), (245, 240, 232)).save(
            run_dir / "final-mockups" / "desktop" / "part-02.png"
        )
    if with_mobile:
        Image.new("RGB", (390, 2200), (26, 26, 46)).save(
            run_dir / "final-mockups" / "mobile" / "part-01.png"
        )
    if with_pages:
        Image.new("RGB", (1440, 2900), (30, 30, 50)).save(run_dir / "1440.png")
        Image.new("RGB", (390, 4700), (35, 35, 55)).save(run_dir / "390.png")
    return run_dir


class TestCompareSheetMissingSide(unittest.TestCase):
    def test_missing_mobile_side_exits_1(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = make_run_dir(Path(td), with_mobile=False)
            proc = run([SCRIPTS / "compare_sheet.py", run_dir], None)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("final-mockups/mobile/part-*.png", proc.stdout)

    def test_missing_desktop_side_exits_1(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = make_run_dir(Path(td), with_desktop=False)
            proc = run([SCRIPTS / "compare_sheet.py", run_dir], None)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("final-mockups/desktop/part-*.png", proc.stdout)

    def test_missing_page_screenshot_exits_1(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = make_run_dir(Path(td), with_pages=False)
            proc = run([SCRIPTS / "compare_sheet.py", run_dir], None)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("1440.png", proc.stdout)
            self.assertIn("390.png", proc.stdout)

    def test_missing_run_dir_exits_2(self):
        proc = run([SCRIPTS / "compare_sheet.py", "/nonexistent-run-xyz"], None)
        self.assertEqual(proc.returncode, 2)


class TestCompareSheetHappyPath(unittest.TestCase):
    def test_full_run_writes_compare_pieces(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = make_run_dir(Path(td))
            run([SCRIPTS / "compare_sheet.py", run_dir], 0)
            compare_dir = run_dir / "responsive-html" / "compare"
            files = sorted(p.name for p in compare_dir.glob("compare-*.png"))
            self.assertTrue(files, "no compare files written")
            for name in files:
                self.assertRegex(name, r"^compare-(390|1440)-\d{2}\.png$")

    def test_label_bar_and_layout(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = make_run_dir(Path(td))
            run([SCRIPTS / "compare_sheet.py", run_dir, "--widths", "1440"], 0)
            piece = next(
                (run_dir / "responsive-html" / "compare").glob("compare-1440-01.png")
            )
            im = Image.open(piece)
            # width = 2 * label_width + gap
            self.assertEqual(im.width, 1440 * 2 + compare_sheet.GAP)
            # label bar height at top
            self.assertGreaterEqual(im.height, compare_sheet.LABEL_BAR_HEIGHT)
            # dark text pixels exist in the label bar
            px = im.convert("RGB").load()
            dark = sum(
                1
                for x in range(0, min(300, im.width))
                for y in range(0, compare_sheet.LABEL_BAR_HEIGHT)
                if sum(px[x, y][:3]) < 200
            )
            self.assertGreater(dark, 10, "no label text in the label bar")


class TestCompareSheetUnits(unittest.TestCase):
    def test_stitch_parts_orders_and_stacks(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            Image.new("RGB", (100, 50), (255, 0, 0)).save(td / "part-02.png")
            Image.new("RGB", (100, 30), (0, 0, 255)).save(td / "part-01.png")
            stitched = compare_sheet.stitch_parts(
                compare_sheet.list_part_files(td)
            )
            self.assertEqual(stitched.size, (100, 80))
            # first written part-01 (blue) is on top
            self.assertEqual(stitched.getpixel((50, 10)), (0, 0, 255))
            # then part-02 (red) below
            self.assertEqual(stitched.getpixel((50, 60)), (255, 0, 0))

    def test_stitch_resizes_mismatched_widths(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            Image.new("RGB", (100, 50), (255, 0, 0)).save(td / "part-01.png")
            Image.new("RGB", (200, 60), (0, 255, 0)).save(td / "part-02.png")
            stitched = compare_sheet.stitch_parts(
                compare_sheet.list_part_files(td)
            )
            self.assertEqual(stitched.width, 100)
            self.assertEqual(stitched.height, 50 + 30)  # 200x60 -> 100x30

    def test_list_part_files_ignores_non_part_files(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            Image.new("RGB", (10, 10), "white").save(td / "part-01.png")
            Image.new("RGB", (10, 10), "white").save(td / "other.png")
            Image.new("RGB", (10, 10), "white").save(td / "part-bad.png")
            files = compare_sheet.list_part_files(td)
            self.assertEqual([f.name for f in files], ["part-01.png"])

    def test_make_sheet_splits_at_max_height(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            mock = Image.new("RGB", (390, 9000), (26, 26, 46))
            page = Image.new("RGB", (390, 9000), (245, 240, 232))
            out = td / "compare-390-01.png"
            count = compare_sheet.make_sheet(390, mock, page, out)
            self.assertGreater(count, 1)
            pieces = sorted(td.glob("compare-390-*.png"))
            self.assertEqual(len(pieces), count)
            for piece in pieces:
                im = Image.open(piece)
                self.assertLessEqual(im.height, compare_sheet.MAX_SHEET_HEIGHT)
                self.assertEqual(im.width, 390 * 2 + compare_sheet.GAP)
                im.close()

    def test_parse_widths_valid(self):
        self.assertEqual(render_page.parse_widths("320,390,1440"), [320, 390, 1440])
        self.assertEqual(render_page.parse_widths("390"), [390])
        self.assertEqual(render_page.parse_widths("390,390,1440"), [390, 1440])

    def test_parse_widths_invalid(self):
        with self.assertRaises(ValueError):
            render_page.parse_widths("abc")
        with self.assertRaises(ValueError):
            render_page.parse_widths("0")
        with self.assertRaises(ValueError):
            render_page.parse_widths("")
        with self.assertRaises(ValueError):
            render_page.parse_widths("-5")

    def test_split_parts_max_height(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            full = td / "full.png"
            Image.new("RGB", (800, 9500), (26, 26, 46)).save(full)
            parts = render_page.split_parts(full, td)
            self.assertEqual([p.name for p in parts],
                             ["part-01.png", "part-02.png", "part-03.png"])
            sizes = [Image.open(p).size for p in parts]
            self.assertEqual(sizes[0], (800, 4000))
            self.assertEqual(sizes[1], (800, 4000))
            self.assertEqual(sizes[2], (800, 1500))
            for p in parts:
                Image.open(p).close()

    def test_missing_html_exits_2(self):
        proc = run([SCRIPTS / "render_page.py", "/nonexistent.html", "--out",
                    "/tmp/rp-test-out"], None)
        self.assertEqual(proc.returncode, 2)

    def test_bad_widths_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            html = Path(td) / "t.html"
            html.write_text("<html><body>hi</body></html>")
            proc = run([SCRIPTS / "render_page.py", html, "--out", td,
                        "--widths", "abc"], None)
            self.assertEqual(proc.returncode, 2)


@unittest.skipUnless(PLAYWRIGHT_OK, "Playwright + Chromium not available")
class TestRenderPagePlaywright(unittest.TestCase):
    def test_render_ok_and_parts(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            Image.new("RGB", (1200, 600), (201, 162, 39)).save(td / "dot.png")
            html = td / "page.html"
            html.write_text(
                "<!doctype html><html><head><style>"
                "section{height:900px}img{width:100%;display:block}"
                "</style></head><body>"
                "<section>one</section><img src='dot.png' alt='dot'>"
                "<section>two</section><section>three</section>"
                "</body></html>"
            )
            out = td / "out"
            run([SCRIPTS / "render_page.py", html, "--out", out,
                 "--widths", "390,1440"], 0)
            self.assertTrue((out / "390.png").is_file())
            self.assertTrue((out / "1440.png").is_file())
            # multi-width: part files are per-width subdirs, never clobbered
            parts_390 = sorted((out / "390").glob("part-*.png"))
            parts_1440 = sorted((out / "1440").glob("part-*.png"))
            self.assertTrue(parts_390, "no 390 part files")
            self.assertTrue(parts_1440, "no 1440 part files")
            for p in parts_390 + parts_1440:
                im = Image.open(p)
                self.assertLessEqual(im.height, render_page.MAX_PART_HEIGHT)
                im.close()

    def test_single_width_parts_are_flat(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            html = td / "page.html"
            html.write_text("<!doctype html><html><body style='height:3000px'>"
                            "x</body></html>")
            out = td / "out"
            run([SCRIPTS / "render_page.py", html, "--out", out,
                 "--widths", "1440"], 0)
            # single width: flat part-NN.png next to the full screenshot
            self.assertTrue((out / "part-01.png").is_file())
            self.assertFalse((out / "1440" / "part-01.png").exists())

    def test_unloadable_image_exits_1_and_names_it(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            html = td / "broken.html"
            html.write_text(
                "<!doctype html><html><body>"
                "<img src='missing-file.png' alt='ghost'>"
                "</body></html>"
            )
            proc = run([SCRIPTS / "render_page.py", html, "--out", td / "out",
                        "--widths", "390"], None)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("missing-file.png", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)