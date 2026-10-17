#!/usr/bin/env python3
"""Tests for Item 15 (layout metrics in validate_page.py), Item 16
(structural drift in compare_sheet.py), and the Amendment 6 deltas
(declared exemptions, V6-BASELINE warn family).

Two layers:
  - Pure-logic unit tests over synthetic LAYOUT_JS-shaped data. These run
    anywhere, no browser needed: the metrics are pure Python over the
    extracted geometry by design.
  - Playwright end-to-end tests (skipped, not failed, when Playwright or
    Chromium is unavailable): page_good must PASS all six metrics,
    page_boxy must FAIL at least signature monotony, image ratio monotony,
    and repeated card grid, and page_declared must PASS through the
    declared-exemption path while the same page without its records FAILs.
"""
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
FIXTURES = ROOT / "tests" / "fixtures"
PY = sys.executable


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vp = _load("validate_page")
cs = _load("compare_sheet")

try:
    from playwright.sync_api import sync_playwright

    _probe_dir = tempfile.mkdtemp(prefix="skill71-probe-")
    try:
        with sync_playwright() as p:
            _probe = p.chromium.launch_persistent_context(
                _probe_dir, headless=True)
            _probe.close()
    finally:
        shutil.rmtree(_probe_dir, ignore_errors=True)
    PLAYWRIGHT_OK = True
except Exception:
    PLAYWRIGHT_OK = False


def rect(left, top, width, height):
    return {"x": left, "y": top, "left": left, "top": top,
            "right": left + width, "bottom": top + height,
            "width": width, "height": height}


def make_section(bg="rgb(26, 26, 46)", align="left", images=None,
                 content_span=0.86, heading=32.0, body=18.0, cols=1):
    sec_rect = rect(0, 0, 1440, 600)
    children = []
    if cols <= 1:
        children = [{"selector": "div", "rect": rect(100, 0, 1240, 600),
                     "textAlign": align, "display": "block", "hasText": True}]
    else:
        w = 1240 // cols
        children = [{"selector": "div",
                     "rect": rect(100 + i * (w + 10), 0, w, 600),
                     "textAlign": align, "display": "block", "hasText": True}
                    for i in range(cols)]
    span_w = int(1440 * content_span)
    return {
        "index": 0, "selector": "section", "id": None, "rect": sec_rect,
        "background": bg, "display": "block", "gridColumns": "none",
        "flexDirection": "row", "children": children,
        "images": images or [],
        "texts": [{"selector": "p", "textAlign": align, "fontSize": body}],
        "headingFontSize": heading, "bodyFontSize": body,
        "contentRects": [rect((1440 - span_w) // 2, 0, span_w, 600)],
    }


def make_image(left, width, height):
    return {"selector": "img", "rect": rect(left, 0, width, height),
            "width": width, "height": height, "slot": None}


def layout_data(sections, images=None, ctas=None, groups=None):
    return {"sections": sections, "siblingGroups": groups or [],
            "ctas": ctas or [], "contentImages": images or []}


def content_images(ratios):
    return [{"selector": "img", "width": 800, "height": 800 / r,
             "ratio": r, "slot": None} for r in ratios]


NO_EXEMPTIONS = {"traits": set(), "style_ids": [], "series": False,
                 "per_section": {}}


def metrics(data, thresholds=None, exemptions=None):
    th = dict(vp.DEFAULT_LAYOUT_THRESHOLDS)
    if thresholds:
        th.update(thresholds)
    return vp.compute_layout_metrics(
        data, th, exemptions=exemptions or NO_EXEMPTIONS)


class TestSignature(unittest.TestCase):
    def test_signature_components(self):
        s = make_section()
        self.assertEqual(
            vp.section_signature(s),
            "cols=1|img=none|align=left|bg=rgb(26,26,46)")

    def test_signature_changes_with_background(self):
        a = vp.section_signature(make_section(bg="rgb(1, 1, 1)"))
        b = vp.section_signature(make_section(bg="rgb(2, 2, 2)"))
        self.assertNotEqual(a, b)

    def test_placement_classes(self):
        sec = make_section()
        self.assertEqual(vp.image_placement_class(sec), "none")
        left = make_section(images=[make_image(100, 400, 300)])
        self.assertEqual(vp.image_placement_class(left), "left")
        right = make_section(images=[make_image(940, 400, 300)])
        self.assertEqual(vp.image_placement_class(right), "right")
        full = make_section(images=[make_image(0, 1400, 400)])
        self.assertEqual(vp.image_placement_class(full), "full-bleed")


class TestSixMetrics(unittest.TestCase):
    def test_signature_monotony_fails(self):
        data = layout_data([make_section() for _ in range(6)])
        res = metrics(data)
        self.assertTrue(any("signature monotony" in f
                            for f in res["failures"]), res)

    def test_signature_diversity_passes(self):
        secs = [make_section(bg=f"rgb({i}, {i}, {i})") for i in range(6)]
        res = metrics(layout_data(secs))
        self.assertFalse(res["failures"], res)
        self.assertTrue(any("signature diversity" in p
                            for p in res["passes"]))

    def test_ratio_monotony_fails_at_three_plus(self):
        data = layout_data([make_section()], images=content_images(
            [1.78, 1.78, 1.79, 1.77]))
        res = metrics(data)
        self.assertTrue(any("image ratio monotony" in f
                            for f in res["failures"]), res)

    def test_ratio_diversity_passes_and_two_images_skip(self):
        data = layout_data([make_section()], images=content_images(
            [2.95, 2.0, 1.0, 1.5]))
        self.assertFalse(metrics(data)["failures"])
        data2 = layout_data([make_section()], images=content_images(
            [1.78, 1.78]))
        self.assertFalse(any("ratio" in f
                             for f in metrics(data2)["failures"]))

    def test_centering_fails_over_threshold(self):
        secs = [make_section(align="center", bg=f"rgb({i},{i},{i})")
                for i in range(6)]
        res = metrics(layout_data(secs))
        self.assertTrue(any("centering monotony" in f
                            for f in res["failures"]), res)

    def test_card_grid_fails_and_allowlist_passes(self):
        kid = {"selector": "div.card", "width": 260, "height": 340,
               "structure": "div(img,h3,p)"}
        groups = [{"parent": "div.cards", "children": [dict(kid) for _ in range(4)]}]
        res = metrics(layout_data([make_section()], groups=groups))
        self.assertTrue(any("repeated card grid" in f
                            for f in res["failures"]), res)
        res2 = metrics(layout_data([make_section()], groups=groups),
                       thresholds={"card_grid_allowlist": ["div.cards"]})
        self.assertFalse(any("card grid" in f for f in res2["failures"]))

    def test_empty_width_fails(self):
        res = metrics(layout_data([make_section(content_span=0.4)]))
        self.assertTrue(any("empty width" in f for f in res["failures"]))

    def test_cta_sameness_fails_and_single_design_declares(self):
        cta = {"selector": "button.cta", "width": 134, "height": 60,
               "background": "rgb(26, 26, 46)"}
        data = layout_data([make_section()],
                           ctas=[dict(cta) for _ in range(3)])
        res = metrics(data)
        self.assertTrue(any("CTA sameness" in f for f in res["failures"]))
        res2 = metrics(data, thresholds={"single_cta_design": True})
        self.assertFalse(res2["failures"])
        self.assertTrue(any("CTA sameness" in d for d in res2["declared"]))


class TestCardGridAllowlistDocs(unittest.TestCase):
    """Item 9: the card_grid_allowlist relief is documented in the brand
    schema and seeded in the intake template, so mandated editorial
    structures are declared deliberately, not discovered by failure.
    No metric behavior and no threshold values change in this item."""

    def _editorial_groups(self):
        # The run's four flagged clusters, in synthetic form: persona
        # rows, inclusion rows, step rows, and letter paragraphs.
        def group(parent, structure, width, height):
            kid = {"selector": "div", "width": width, "height": height,
                   "structure": structure}
            return {"parent": parent,
                    "children": [dict(kid) for _ in range(4)]}
        return [
            group("section.persona-rows", "div(img,h3,p)", 1240, 160),
            group("section.inclusion-rows", "div(h3,p)", 1240, 140),
            group("section.step-rows", "div(span,h3,p)", 1240, 150),
            group("section.letter-body", "div(p)", 1100, 96),
        ]

    def test_undeclared_editorial_structures_fail(self):
        res = metrics(layout_data([make_section()],
                                  groups=self._editorial_groups()))
        grid_failures = [f for f in res["failures"]
                         if "repeated card grid" in f]
        self.assertEqual(len(grid_failures), 4, res["failures"])
        self.assertEqual(res["measured"]["card_grid_failures"], 4)
        self.assertTrue(all("banned repeated card grid" in f
                            for f in grid_failures), grid_failures)

    def test_pair_form_declarations_pass(self):
        allow = ["section.persona-rows div(img,h3,p)",
                 "section.inclusion-rows div(h3,p)",
                 "section.step-rows div(span,h3,p)",
                 "section.letter-body div(p)"]
        res = metrics(layout_data([make_section()],
                                  groups=self._editorial_groups()),
                      thresholds={"card_grid_allowlist": allow})
        self.assertFalse(any("card grid" in f for f in res["failures"]),
                         res)
        self.assertEqual(res["measured"]["card_grid_failures"], 0)
        self.assertTrue(any("card grid allowlisted" in p
                            for p in res["passes"]), res["passes"])

    def test_failure_message_names_brand_key(self):
        res = metrics(layout_data([make_section()],
                                  groups=self._editorial_groups()))
        blob = "\n".join(res["failures"])
        self.assertIn("layout_thresholds.card_grid_allowlist", blob)

    def test_schema_documents_allowlist_key(self):
        schema = json.loads(
            (ROOT / "assets" / "brand" / "brand.schema.json").read_text(
                encoding="utf-8"))
        thresholds = schema["properties"]["layout_thresholds"]
        self.assertIn("card_grid_allowlist", thresholds["properties"])
        self.assertIn("parent selector", thresholds["description"])
        self.assertIn("structure signature", thresholds["description"])
        self.assertEqual(thresholds["properties"]
                         ["card_grid_min_repetitions"]["minimum"], 1)

    def test_template_seeds_allowlist(self):
        template = json.loads(
            (ROOT / "assets" / "brand" /
             "client-brand.template.json").read_text(encoding="utf-8"))
        seeded = template["layout_thresholds"]
        self.assertEqual(seeded["card_grid_allowlist"], [])
        for key, value in vp.DEFAULT_LAYOUT_THRESHOLDS.items():
            self.assertEqual(seeded[key], value, key)


class TestDeclaredExemptions(unittest.TestCase):
    def test_centered_and_sparse_traits_exempt(self):
        secs = [make_section(align="center", content_span=0.4,
                             bg=f"rgb({i},{i},{i})") for i in range(4)]
        ex = {"traits": {"centered composition", "sparse negative space"},
              "style_ids": ["CIS-35"], "series": False, "per_section": {}}
        res = metrics(layout_data(secs), exemptions=ex)
        self.assertFalse(res["failures"], res)
        self.assertTrue(any("centering" in d for d in res["declared"]))
        self.assertTrue(any("empty width" in d for d in res["declared"]))
        self.assertTrue(all("CIS-35" in d for d in res["declared"]))

    def test_declared_series_exempts_ratio(self):
        data = layout_data([make_section()],
                           images=content_images([1.78, 1.78, 1.78]))
        ex = {"traits": set(), "style_ids": ["CIS-35"], "series": True,
              "per_section": {}}
        res = metrics(data, exemptions=ex)
        self.assertFalse(res["failures"])
        self.assertTrue(any("declared series" in d
                            for d in res["declared"]))

    def test_no_records_no_exemptions(self):
        data = layout_data([make_section()],
                           images=content_images([1.78, 1.78, 1.78]))
        res = metrics(data, exemptions=NO_EXEMPTIONS)
        self.assertTrue(any("ratio monotony" in f
                            for f in res["failures"]))


class TestV6Baseline(unittest.TestCase):
    def test_frame_ratio_mismatch_warns(self):
        data = {1440: layout_data(
                    [make_section()],
                    images=[{"selector": "img", "width": 600,
                             "height": 600, "ratio": 1.0,
                             "slot": "IMG-001"}]),
                "wrap": {}}
        image_map = [{"id": "IMG-001", "desktop_slot_px": 600,
                      "desktop_slot_h_px": 900}]
        res = vp.compute_v6_baseline(data, image_map,
                                     vp.DEFAULT_LAYOUT_THRESHOLDS)
        self.assertTrue(any("V6-BASELINE: frame ratio" in w
                            for w in res["warnings"]), res)

    def test_frame_ratio_match_is_quiet(self):
        data = {1440: layout_data(
                    [make_section()],
                    images=[{"selector": "img", "width": 600,
                             "height": 900, "ratio": 600 / 900,
                             "slot": "IMG-001"}]),
                "wrap": {}}
        image_map = [{"id": "IMG-001", "desktop_slot_px": 600,
                      "desktop_slot_h_px": 900}]
        res = vp.compute_v6_baseline(data, image_map,
                                     vp.DEFAULT_LAYOUT_THRESHOLDS)
        self.assertFalse(res["warnings"], res)


class TestDriftCompare(unittest.TestCase):
    def test_identical_structures_pass(self):
        secs = [make_section(), make_section(bg="rgb(9, 9, 9)")]
        failures, table = cs.compare_section_structures(secs, secs)
        self.assertFalse(failures, failures)
        self.assertTrue(all(r["status"] == "ok" for r in table))

    def test_count_mismatch_fails(self):
        failures, _ = cs.compare_section_structures(
            [make_section()], [make_section(), make_section()])
        self.assertTrue(any("section count differs" in f
                            for f in failures))

    def test_order_mismatch_fails(self):
        a = make_section(bg="rgb(1, 1, 1)")
        b = make_section(bg="rgb(2, 2, 2)")
        failures, _ = cs.compare_section_structures([a, b], [b, a])
        self.assertTrue(any("section order differs" in f
                            for f in failures))

    def test_placement_change_fails(self):
        m = make_section(images=[make_image(100, 400, 300)])
        p = make_section(images=[make_image(940, 400, 300)])
        failures, table = cs.compare_section_structures([m], [p])
        self.assertTrue(any("image placement changed" in f
                            for f in failures), failures)
        self.assertEqual(table[0]["status"], "drift")

    def test_heading_ratio_drift_fails_and_tolerance_passes(self):
        m = make_section(heading=32.0, body=18.0)
        p = make_section(heading=20.0, body=18.0)
        failures, _ = cs.compare_section_structures([m], [p])
        self.assertTrue(any("heading-to-body" in f for f in failures))
        p2 = make_section(heading=30.0, body=18.0)
        failures2, _ = cs.compare_section_structures([m], [p2])
        self.assertFalse(failures2, failures2)


def run_validator(html, brand, extra=(), timeout=300):
    return subprocess.run(
        [PY, SCRIPTS / "validate_page.py", html, "--brand", brand, *extra],
        text=True, capture_output=True, timeout=timeout)


@unittest.skipUnless(PLAYWRIGHT_OK, "Playwright + Chromium not available")
class TestFixturesEndToEnd(unittest.TestCase):
    def test_good_passes_all_six_metrics(self):
        good = FIXTURES / "page_good"
        with tempfile.TemporaryDirectory() as td:
            proc = run_validator(
                good / "index.html", good / "brand-fixture.json",
                ["--mode", "page", "--run-dir", td,
                 "--image-map", good / "image-map.json",
                 "--copy", good / "public-copy.md",
                 "--intake", good / "intake.json"])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            for line in ("section signature diversity",
                         "image ratio diversity", "centering ratio",
                         "repeated card grid", "empty width", "CTA variety"):
                self.assertIn(f"LAYOUT PASS: {line}", proc.stdout)
            report = json.loads(
                (Path(td) / "responsive-html" /
                 "validate-page.json").read_text(encoding="utf-8"))
            self.assertIn("layout", report["checks"])
            self.assertEqual(
                report["checks"]["layout"]["measured"]["section_count"], 6)

    def test_boxy_fails_metrics_1_2_4(self):
        boxy = FIXTURES / "page_boxy"
        with tempfile.TemporaryDirectory() as td:
            proc = run_validator(
                boxy / "index.html", boxy / "brand-fixture.json",
                ["--mode", "page", "--run-dir", td,
                 "--copy", boxy / "public-copy.md",
                 "--intake", boxy / "intake.json"])
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            for needle in ("section signature monotony",
                           "image ratio monotony", "repeated card grid"):
                self.assertIn(needle, proc.stdout)

    def test_declared_passes_via_exemptions(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            shutil.copytree(FIXTURES / "page_declared", run_dir)
            proc = run_validator(
                run_dir / "index.html", run_dir / "brand-fixture.json",
                ["--mode", "page", "--run-dir", run_dir,
                 "--copy", run_dir / "public-copy.md",
                 "--intake", run_dir / "intake.json"])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("LAYOUT DECLARED:", proc.stdout)
            self.assertIn("CIS-35", proc.stdout)

    def test_declared_page_without_records_fails(self):
        src = FIXTURES / "page_declared"
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            for name in ("index.html", "brand-fixture.json", "intake.json",
                         "public-copy.md", "logo.png", "img.png"):
                shutil.copy(src / name, run_dir / name)
            proc = run_validator(
                run_dir / "index.html", run_dir / "brand-fixture.json",
                ["--mode", "page", "--run-dir", run_dir,
                 "--copy", run_dir / "public-copy.md",
                 "--intake", run_dir / "intake.json"])
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("centering monotony", proc.stdout)
            self.assertIn("empty width", proc.stdout)
            self.assertIn("image ratio monotony", proc.stdout)


@unittest.skipUnless(PLAYWRIGHT_OK, "Playwright + Chromium not available")
class TestCompareSheetDriftEndToEnd(unittest.TestCase):
    def _make_run(self, base, mockup_src, page_src):
        run_dir = base / "run"
        (run_dir / "final-mockups" / "desktop").mkdir(parents=True)
        (run_dir / "final-mockups" / "mobile").mkdir(parents=True)
        (run_dir / "responsive-html").mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (1440, 800), (26, 26, 46)).save(
            run_dir / "final-mockups" / "desktop" / "part-01.png")
        Image.new("RGB", (390, 800), (26, 26, 46)).save(
            run_dir / "final-mockups" / "mobile" / "part-01.png")
        Image.new("RGB", (1440, 800), (26, 26, 46)).save(run_dir / "1440.png")
        Image.new("RGB", (390, 800), (26, 26, 46)).save(run_dir / "390.png")
        for dest, src in (("final-mockups", mockup_src),
                          ("responsive-html", page_src)):
            target = run_dir / dest
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy(f, target / ("mockup.html"
                                             if dest == "final-mockups"
                                             and f.name == "index.html"
                                             else f.name))
        return run_dir

    def test_matching_structure_passes_with_report(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run(Path(td), FIXTURES / "page_good",
                                     FIXTURES / "page_good")
            proc = subprocess.run(
                [PY, SCRIPTS / "compare_sheet.py", run_dir],
                text=True, capture_output=True, timeout=300)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("DRIFT OK", proc.stdout)
            report = json.loads(
                (run_dir / "responsive-html" / "compare" /
                 "compare-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["drift"]["status"], "pass")
            self.assertEqual(
                len(report["drift"]["widths"]["1440"]["table"]), 6)

    def test_drifted_structure_fails_with_report(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._make_run(Path(td), FIXTURES / "page_good",
                                     FIXTURES / "page_boxy")
            proc = subprocess.run(
                [PY, SCRIPTS / "compare_sheet.py", run_dir],
                text=True, capture_output=True, timeout=300)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("DRIFT:", proc.stdout)
            report = json.loads(
                (run_dir / "responsive-html" / "compare" /
                 "compare-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["drift"]["status"], "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
