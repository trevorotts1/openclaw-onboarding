#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIX = Path(__file__).resolve().parent / "fixtures"
PY = sys.executable


def run(args, expect=0, cwd=None):
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != expect:
        print("COMMAND:", " ".join(str(x) for x in args))
        print("STDOUT:\n", proc.stdout)
        print("STDERR:\n", proc.stderr)
        raise AssertionError(f"Expected return code {expect}, got {proc.returncode}")
    return proc


def test_state():
    run([PY, str(SCRIPTS / "validate_state.py"), str(FIX / "state-valid.json")], 0)
    run([PY, str(SCRIPTS / "validate_state.py"), str(FIX / "state-invalid.json")], 1)


def test_prompts():
    # The padded 1.0.0-era fixture is no longer a valid prompt under the C4
    # padding rule; the compliant fixture is tests/fixtures/prompt_good.txt.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fit_prompt
    with tempfile.TemporaryDirectory() as td:
        fitted = fit_prompt.fit_file(FIX / "prompt_good.txt", Path(td) / "prompt_fitted.txt")
        run([PY, str(SCRIPTS / "validate_prompt.py"), fitted, "--sauce-only"], 0)
    run([PY, str(SCRIPTS / "validate_prompt.py"), str(FIX / "prompt-valid.md")], 1)
    run([PY, str(SCRIPTS / "validate_prompt.py"), str(FIX / "prompt-too-short.md")], 1)


def test_image_manifest():
    run([PY, str(SCRIPTS / "validate_image_manifest.py"), str(FIX / "image-manifest-valid.json")], 0)
    run([PY, str(SCRIPTS / "validate_image_manifest.py"), str(FIX / "image-manifest-invalid.json")], 1)


def test_public_copy():
    run([PY, str(SCRIPTS / "validate_public_copy.py"), str(FIX / "public-copy-valid.md")], 0)
    run([PY, str(SCRIPTS / "validate_public_copy.py"), str(FIX / "public-copy-invalid.md")], 1)


def test_pdf_pipeline():
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise AssertionError("Pillow is required for the PDF smoke test") from exc

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i in range(1, 4):
            im = Image.new("RGB", (900, 1400), "white")
            d = ImageDraw.Draw(im)
            d.text((50, 50), f"Desktop wireframe part {i}", fill="black")
            im.save(td / f"desktop-wireframe-part-{i:02d}.png")

        manifest = {
            "category": "desktop-wireframes",
            "output": "desktop-wireframes.pdf",
            "pages": [
                {"path": f"desktop-wireframe-part-{i:02d}.png", "label": f"Part {i:02d}"}
                for i in range(1, 4)
            ],
        }
        manifest_path = td / "review-set.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        run([PY, str(SCRIPTS / "combine_review_pdf.py"), str(manifest_path)], 0)
        run([PY, str(SCRIPTS / "validate_review_pdf.py"), str(manifest_path)], 0)


def test_intake_founder_photo_forms():
    # Update plan Item 10: write_intake refuses a brand founder_photos entry
    # that is in none of the forms validate_page.founder_allowed_hashes
    # accepts, at intake, naming the entry and the accepted forms.
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        (run_dir / "private").mkdir(parents=True)
        brand_path = run_dir / "private" / "brand.json"
        photo = run_dir / "private" / "founder.jpg"
        photo.write_bytes(b"fake-jpeg-bytes")

        def intake_with(photos):
            brand_path.write_text(json.dumps({"founder_photos": photos}), encoding="utf-8")
            return subprocess.run([
                PY, str(SCRIPTS / "write_intake.py"), str(run_dir),
                "--page-version", "standard", "--brand-owner", "Fixture",
                "--brand-file", "private/brand.json", "--image-cap", "1",
            ], text=True, capture_output=True)

        bare = "93eecdc2044f27b2c5a2c6836d2e2b020dcd6865cde7c4278a5abd52b27b336a"
        proc = intake_with(f"/photos/founder.jpg Trevor's supplied founder photo, sha256 {bare}")
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "founder_photos" in proc.stdout and "sha256:" in proc.stdout, proc.stdout
        proc = intake_with("no-such-photo.jpg")
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert intake_with(bare).returncode == 0
        assert intake_with([f"sha256:{bare}"]).returncode == 0
        assert intake_with(["founder.jpg"]).returncode == 0
        assert intake_with("TREVOR_MUST_SUPPLY").returncode == 0


def test_installer_dry_run():
    with tempfile.TemporaryDirectory() as td:
        run([
            PY, str(SCRIPTS / "install_local.py"),
            "--runtime", "custom",
            "--target-root", td,
            "--dry-run",
        ], 0)


def main():
    tests = [
        test_state,
        test_prompts,
        test_image_manifest,
        test_public_copy,
        test_pdf_pipeline,
        test_intake_founder_photo_forms,
        test_installer_dry_run,
    ]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"ALL PASS: {len(tests)} smoke tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
