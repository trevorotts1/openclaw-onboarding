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
    run([PY, str(SCRIPTS / "validate_prompt.py"), str(FIX / "prompt_good.txt"),
         "--sauce-only"], 0)
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
        test_installer_dry_run,
    ]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"ALL PASS: {len(tests)} smoke tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
