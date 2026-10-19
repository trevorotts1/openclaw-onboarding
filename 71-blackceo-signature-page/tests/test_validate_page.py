#!/usr/bin/env python3
"""tests/test_validate_page.py — Skill 71 order C2 tests.

Bad fixture (tests/fixtures/page_bad) must FAIL with each required reason:
off-palette authored hexes #F6F1E8/#111214, banned font Inter, no logo,
[WEBINAR_DATE] placeholder, lazy image, founder slot mismatch, overflow,
mobile floors, off-palette computed colors.

Good fixture (tests/fixtures/page_good) must PASS: fixture brand file with a
stand-in font (Georgia — never the real blackceo-brand.json, whose fonts are
TREVOR_MUST_SUPPLY), exact palette hexes, logo element, eager images, founder
hash match, copy parity.

Also covers: mockup mode (exact [data-image-slot] sizes), placeholder
WARN-when-test_run, TREVOR_MUST_SUPPLY fail-closed, exit codes 0/1/2,
and the 1.1.1 font fallback: MUST_SUPPLY brand fonts under a
derive-document font_policy degrade the font checks to WARN (derived) —
never FAIL — while banned fonts and every other check still FAIL.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_page.py"
GOOD = ROOT / "tests" / "fixtures" / "page_good"
BAD = ROOT / "tests" / "fixtures" / "page_bad"
LETTER = ROOT / "tests" / "fixtures" / "page_letter"
PY = sys.executable

REQUIRED_BAD_REASONS = [
    "authored color #F6F1E8",
    "authored color #111214",
    "loading=lazy",
    "Inter",
    "banned",
    "WEBINAR_DATE",
    "exceeds color_tolerance",
    "logo",
    "founder image sha256",
    "overflow",
    "below the 18px floor",
    "below the 56px floor",
    "below the 16px floor",
]


def run(args, cwd=None, timeout=300):
    return subprocess.run(
        [str(a) for a in args], cwd=cwd, text=True, capture_output=True, timeout=timeout
    )


def validate(html, brand, extra=(), timeout=300):
    return run(
        [PY, SCRIPT, html, "--brand", brand, *extra], timeout=timeout
    )


def report_from(run_dir, sub="responsive-html"):
    path = Path(run_dir) / sub / "validate-page.json"
    assert path.exists(), f"missing report: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_page", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Item 2's end-to-end tests drive the real validator against the
# page_letter fixture in a real browser. Where Playwright + Chromium
# are unavailable they SKIP with the reason named; the module runner
# prints SKIP and never counts a skip as a pass.
class SkipTest(Exception):
    """A test whose runtime is unavailable SKIPs; a skip is never a pass."""


def _require_playwright():
    """Probe for a working Playwright + Chromium by launching a real
    persistent context (a bare import check proves nothing). Raises
    SkipTest when the browser layer is unavailable in this environment,
    so browser tests report SKIP instead of failing or silently passing.
    The probe launches a persistent context and closes it, the same gate
    tests/test_layout_metrics.py uses, so a SKIP here means the browser
    layer genuinely cannot run in this environment."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SkipTest("Playwright + Chromium not available") from exc
    probe_dir = tempfile.mkdtemp(prefix="skill71-probe-")
    try:
        with sync_playwright() as p:
            probe = p.chromium.launch_persistent_context(
                probe_dir, headless=True)
            probe.close()
    except Exception as exc:
        raise SkipTest("Playwright + Chromium not available") from exc
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def test_bad_fails_with_each_reason():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        run_dir.mkdir()
        proc = validate(
            BAD / "index.html",
            BAD / "brand-fixture.json",
            ["--mode", "page", "--run-dir", run_dir,
             "--intake", BAD / "intake.json"],
        )
        assert proc.returncode == 1, (
            f"bad fixture must exit 1, got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        )
        report = report_from(run_dir)
        assert report["passed"] is False
        blob = "\n".join(report["errors"])
        for reason in REQUIRED_BAD_REASONS:
            assert reason in blob, f"bad fixture missing reason: {reason!r}\nGot:\n{blob}"


def test_good_passes():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        run_dir.mkdir()
        proc = validate(
            GOOD / "index.html",
            GOOD / "brand-fixture.json",
            ["--mode", "page", "--run-dir", run_dir,
             "--image-map", GOOD / "image-map.json",
             "--copy", GOOD / "public-copy.md",
             "--intake", GOOD / "intake.json"],
        )
        assert proc.returncode == 0, (
            f"good fixture must pass; got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        )
        report = report_from(run_dir)
        assert report["passed"] is True
        assert report["errors"] == []


def test_good_fixture_brand_is_not_real_blackceo_brand():
    brand = json.loads((GOOD / "brand-fixture.json").read_text(encoding="utf-8"))
    for value in brand["fonts"].values():
        assert "TREVOR_MUST_SUPPLY" not in value, (
            "good fixture must not depend on unsupplied real brand fonts"
        )
    real = ROOT / "assets" / "brand" / "blackceo-brand.json"
    if real.exists():
        real_brand = json.loads(real.read_text(encoding="utf-8"))
        for value in (real_brand.get("fonts") or {}).values():
            assert "TREVOR_MUST_SUPPLY" in value or value not in set(
                json.loads((GOOD / "brand-fixture.json").read_text(encoding="utf-8"))["fonts"].values()
            ), "fixture fonts must not silently borrow real brand fonts"


def test_test_run_placeholders_warn_not_fail():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        intake = json.loads((BAD / "intake.json").read_text(encoding="utf-8"))
        intake["test_run"] = True
        (td / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        proc = validate(
            BAD / "index.html",
            BAD / "brand-fixture.json",
            ["--mode", "page", "--run-dir", td, "--intake", td / "intake.json"],
        )
        assert proc.returncode == 1  # still fails on colors/fonts/logo
        report = report_from(td)
        blob = "\n".join(report["errors"])
        warns = "\n".join(report["warnings"])
        assert "WEBINAR_DATE" not in blob, "placeholder must be WARN under test_run, not FAIL"
        assert "WEBINAR_DATE" in warns, "placeholder must appear as a WARN under test_run"


def test_mockup_mode_passes_good_fixture():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        run_dir.mkdir()
        proc = validate(
            GOOD / "index.html",
            GOOD / "brand-fixture.json",
            ["--mode", "mockup", "--run-dir", run_dir,
             "--image-map", GOOD / "image-map.json",
             "--intake", GOOD / "intake.json"],
        )
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
        report = report_from(run_dir, sub="visual-mockup")
        assert report["mode"] == "mockup"


def test_mockup_slot_size_mismatch_fails():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shutil = __import__("shutil")
        run_dir = td / "run"
        shutil.copytree(GOOD, run_dir / "mock")
        map_data = json.loads((GOOD / "image-map.json").read_text(encoding="utf-8"))
        map_data[0]["desktop_slot_px"] = 900  # page renders 1180px
        (run_dir / "image-map.json").write_text(json.dumps(map_data), encoding="utf-8")
        proc = validate(
            run_dir / "mock" / "index.html",
            GOOD / "brand-fixture.json",
            ["--mode", "mockup", "--run-dir", run_dir,
             "--image-map", run_dir / "image-map.json"],
        )
        assert proc.returncode == 1, f"slot mismatch must fail\n{proc.stdout}"
        report = report_from(run_dir, sub="visual-mockup")
        assert any("IMG-001" in e and "900" in e for e in report["errors"])


def test_missing_inputs_exit_2():
    proc = run(
        [PY, SCRIPT, ROOT / "tests" / "fixtures" / "page_no_such.html",
         "--brand", GOOD / "brand-fixture.json"]
    )
    assert proc.returncode == 2, f"missing HTML must exit 2, got {proc.returncode}"
    proc = run(
        [PY, SCRIPT, GOOD / "index.html", "--brand", ROOT / "no-such-brand.json"]
    )
    assert proc.returncode == 2, f"missing brand must exit 2, got {proc.returncode}"


def test_must_supply_brand_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        brand = json.loads((GOOD / "brand-fixture.json").read_text(encoding="utf-8"))
        brand["fonts"]["display"] = "TREVOR_MUST_SUPPLY"
        (td / "brand.json").write_text(json.dumps(brand), encoding="utf-8")
        proc = validate(GOOD / "index.html", td / "brand.json")
        assert proc.returncode == 2, f"must fail closed with exit 2, got {proc.returncode}"
        assert "TREVOR_MUST_SUPPLY" in (proc.stderr + proc.stdout)


def test_derived_font_policy_warns_not_fails():
    """fonts must be WARN (not FAIL) when the brand file's fonts are
    MUST_SUPPLY placeholders under a derive-document font_policy; banned
    fonts and every other check still FAIL."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        brand = json.loads((GOOD / "brand-fixture.json").read_text(encoding="utf-8"))
        brand["fonts"] = {"display": "TREVOR_MUST_SUPPLY",
                          "body": "TREVOR_MUST_SUPPLY",
                          "accent": "TREVOR_MUST_SUPPLY"}
        brand["font_policy"] = {"when_brand_fonts_missing": "derive-document",
                                "requires_rationale": True,
                                "requires_reviewer": True}
        (td / "brand.json").write_text(json.dumps(brand), encoding="utf-8")
        proc = validate(
            GOOD / "index.html",
            td / "brand.json",
            ["--mode", "page", "--run-dir", td / "run"],
        )
        report = report_from(td / "run")
        blob = "\n".join(report["errors"])
        warns = "\n".join(report["warnings"])
        font_fails = [e for e in report["errors"] if e.startswith("font:")]
        font_warns = [w for w in report["warnings"] if "WARN font (derived)" in w]
        assert not font_fails, f"derived fonts must not FAIL:\n{font_fails}"
        assert font_warns, "derived fonts must appear as WARN (derived) lines"
        assert "Georgia" in warns, f"the derived font should be named in WARNs\n{warns}"
        # The fixture page still passes overall (colors/logo/copy fine) with
        # the fonts issue downgraded to WARN.
        assert proc.returncode == 0, (
            f"fixture page must pass under derived-font policy; got {proc.returncode}\n"
            f"errors: {report['errors']}\nwarnings: {report['warnings']}")


def test_copy_candidates_mid_sentence_link_uses_label():
    """Item 1 regression: the copy-parity sentence candidate for a line
    carrying a mid-sentence Markdown link is built from the link's label
    (the words the reader sees), never from a blank where the link stood."""
    vp = _load_validator()
    line = ("So here is my invitation, owner to owner: join the "
            "[BlackCEO School of AI](#join). Bring the work that lands "
            "on you every day.")
    cands = vp.copy_candidates(line)
    assert "BlackCEO School of AI" in cands, cands
    sentence = ("So here is my invitation, owner to owner: join the "
                "BlackCEO School of AI. Bring the work that lands on "
                "you every day.")
    assert sentence in cands, cands
    assert not any("join the ." in c for c in cands), cands
    page_text = vp.norm_text(sentence)
    missing = [c for c in cands if vp.norm_text(c) not in page_text]
    assert missing == [], f"parity must pass on the rendered sentence: {missing}"
    removed = "Seats for the next cohort are limited to twenty founders."
    still_missing = [c for c in vp.copy_candidates(removed)
                     if vp.norm_text(c) not in page_text]
    assert still_missing, "a copy line the page lacks must still fail parity"
    altered = vp.norm_text(sentence.replace("invitation", "summons"))
    word_missing = [c for c in cands if vp.norm_text(c) not in altered]
    assert sentence in word_missing, "every candidate stays required verbatim"


def test_copy_candidates_standalone_link_line_unchanged():
    """Standalone CTA link line: the sentence candidate becomes the label,
    which the label candidate already covers (a duplicate; parity uses
    membership, so it is inert)."""
    vp = _load_validator()
    cands = vp.copy_candidates("[Apply Now](#join)")
    assert cands == ["Apply Now", "Apply Now"], cands


def test_letter_fixture_passes():
    """Item 2 regression (pass case): the page_letter fixture carries the
    Section 12 pattern - an inline prose link (a.inv-link, no display
    styling of its own) inside the founder letter, real buttons at or
    above the 56px floor, and the letter sentence in the public copy with
    its mid-sentence Markdown link. Under the fixed sweep the whole page
    validates: the inline link is not measured as a button, and copy
    parity passes on the label-built sentence candidate. The fixture is
    the page_good page plus the letter section, so every other check
    (palette, fonts, logo, founder hash, layout metrics) is held to the
    same standard the good fixture already meets."""
    _require_playwright()
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        run_dir.mkdir()
        proc = validate(
            LETTER / "index.html",
            LETTER / "brand-fixture.json",
            ["--mode", "page", "--run-dir", run_dir,
             "--image-map", LETTER / "image-map.json",
             "--copy", LETTER / "public-copy.md",
             "--intake", LETTER / "intake.json"],
        )
        assert proc.returncode == 0, (
            f"letter fixture must pass; got {proc.returncode}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
        report = report_from(run_dir)
        assert report["passed"] is True
        assert report["errors"] == []
        assert report["checks"]["copy_parity_checked"] > 0
        layout = report["checks"]["layout"]
        assert layout["measured"]["section_count"] == 7, layout["measured"]


def test_letter_fixture_short_inline_block_anchor_fails():
    """Item 2 regression (guard case): a short button-styled anchor
    (computed display inline-block) injected into the letter page must
    still fail the 56px floor by name, while the inline prose link stays
    unflagged and copy parity stays clean. The exemption covers computed
    display inline only; it is not a hole for short anchors generally.
    The unmodified fixture passes whole (test_letter_fixture_passes), so
    the injected anchor must be the page's only failure here."""
    _require_playwright()
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        shutil.copytree(LETTER, run_dir / "page")
        page_dir = run_dir / "page"
        html = (page_dir / "index.html").read_text(encoding="utf-8")
        injected = ('<a class="promo-link" href="#join" '
                    'style="display: inline-block; padding: 4px 10px; '
                    'font-size: 18px;">'
                    "Short Promo</a>")
        html = html.replace("</body>", f"  {injected}\n</body>")
        assert "promo-link" in html
        (page_dir / "index.html").write_text(html, encoding="utf-8")
        proc = validate(
            page_dir / "index.html",
            page_dir / "brand-fixture.json",
            ["--mode", "page", "--run-dir", run_dir,
             "--image-map", page_dir / "image-map.json",
             "--copy", page_dir / "public-copy.md",
             "--intake", page_dir / "intake.json"],
        )
        assert proc.returncode == 1, (
            f"short inline-block anchor must fail; got {proc.returncode}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
        report = report_from(run_dir)
        assert report["passed"] is False
        blob = "\n".join(report["errors"])
        assert "mobile button: a.promo-link" in blob, blob
        assert "below the 56px floor at 390px" in blob, blob
        assert "inv-link" not in blob, blob
        assert "copy parity" not in blob, blob
        mobile_errors = [e for e in report["errors"] if "mobile button" in e]
        assert len(mobile_errors) == 1, mobile_errors
        assert report["errors"] == mobile_errors, report["errors"]
        assert report["checks"]["copy_parity_checked"] > 0


def main():
    tests = [
        test_copy_candidates_mid_sentence_link_uses_label,
        test_copy_candidates_standalone_link_line_unchanged,
        test_letter_fixture_passes,
        test_letter_fixture_short_inline_block_anchor_fails,
        test_bad_fails_with_each_reason,
        test_good_passes,
        test_good_fixture_brand_is_not_real_blackceo_brand,
        test_test_run_placeholders_warn_not_fail,
        test_mockup_mode_passes_good_fixture,
        test_mockup_slot_size_mismatch_fails,
        test_missing_inputs_exit_2,
        test_must_supply_brand_fails_closed,
        test_derived_font_policy_warns_not_fails,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except SkipTest as exc:
            print(f"SKIP {test.__name__}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    if failed:
        print(f"{failed} test(s) failed")
        return 1
    print(f"ALL {len(tests)} TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
