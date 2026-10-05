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
WARN-when-test_run, TREVOR_MUST_SUPPLY fail-closed, exit codes 0/1/2.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_page.py"
GOOD = ROOT / "tests" / "fixtures" / "page_good"
BAD = ROOT / "tests" / "fixtures" / "page_bad"
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


def main():
    tests = [
        test_bad_fails_with_each_reason,
        test_good_passes,
        test_good_fixture_brand_is_not_real_blackceo_brand,
        test_test_run_placeholders_warn_not_fail,
        test_mockup_mode_passes_good_fixture,
        test_mockup_slot_size_mismatch_fails,
        test_missing_inputs_exit_2,
        test_must_supply_brand_fails_closed,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
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
