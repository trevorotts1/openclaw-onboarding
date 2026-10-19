#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ALLOWED = {
    "desktop-wireframes",
    "mobile-wireframes",
    "desktop-mockups",
    "mobile-mockups",
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_name(category, path):
    name = path.name.lower()
    errors = []
    if category.startswith("desktop") and "mobile" in name:
        errors.append(f"Desktop review set includes a file named as mobile: {path.name}")
    if category.startswith("mobile") and "desktop" in name:
        errors.append(f"Mobile review set includes a file named as desktop: {path.name}")
    if category.endswith("wireframes") and "mockup" in name:
        errors.append(f"Wireframe review set includes a file named as mockup: {path.name}")
    if category.endswith("mockups") and "wireframe" in name:
        errors.append(f"Mockup review set includes a file named as wireframe: {path.name}")
    return errors


# Stage plan (the pinned review-PDF step): for each image stage, where the
# ordered section images live, which review category they are, and the PDF
# name the client sees. One PDF per device per stage; one page per section,
# at the section's native size, so a page break never cuts a section and
# no scaling, cropping or gap is introduced between sections.
REVIEW_DIR = "review-pdfs"
STAGE_PDFS = {
    "desktop-wireframe": [("section-{n:02d}.png", "desktop-wireframes", "wireframes-desktop.pdf")],
    "mobile-tablet": [("section-{n:02d}.png", "mobile-wireframes", "wireframes-mobile.pdf")],
    "visual-mockup": [("desktop/part-{n:02d}.png", "desktop-mockups", "visual-mockups-desktop.pdf"),
                      ("mobile/part-{n:02d}.png", "mobile-mockups", "visual-mockups-mobile.pdf")],
    "final-mockups": [("desktop/part-{n:02d}.png", "desktop-mockups", "final-mockups-desktop.pdf"),
                      ("mobile/part-{n:02d}.png", "mobile-mockups", "final-mockups-mobile.pdf")],
}
# The wireframe stage contract also requires <stage>/wireframe.pdf.
CONTRACT_COPY = {"desktop-wireframe": "wireframe.pdf", "mobile-tablet": "wireframe.pdf"}


def part_label(n):
    return f"Part-{chr(64 + n)}" if n <= 26 else f"Part-{n}"


def discover(run_dir, stage, expect=None):
    """Return [(template, category, pdf_name, [image paths in section order])].

    Raises ValueError (one named line) when a set has a gap, a stray
    higher-numbered section, or does not match the expected section count.
    """
    run_dir = Path(run_dir)
    out = []
    for template, category, name in STAGE_PDFS[stage]:
        pattern = re.compile("^" + re.escape(template).replace(re.escape("{n:02d}"), r"(\d+)") + "$")
        found = {}
        folder = (run_dir / stage / template).parent
        for f in folder.glob("*.png") if folder.is_dir() else []:
            m = pattern.match(str(f.relative_to(run_dir / stage)))
            if m:
                found[int(m.group(1))] = f
        if not found:
            raise ValueError(f"{stage}: no section images match {template.format(n=1)} in {run_dir / stage}")
        want = list(range(1, max(found) + 1))
        if sorted(found) != want:
            raise ValueError(f"{stage}: section images are not contiguous from 01 "
                             f"(have {sorted(found)}); a missing section would leave a gap in {name}")
        if expect is not None and len(found) != expect:
            raise ValueError(f"{stage}: {len(found)} section images for {expect} expected sections in {name}")
        out.append((template, category, name, [found[n] for n in want]))
    return out


def build_stage(run_dir, stage, expect=None, deliver=None):
    """Combine and validate every review PDF of one stage. Returns 0 on pass.

    A PDF that fails its validator is deleted, so a bad PDF never reaches
    the client. With `deliver`, each validated PDF is copied into that
    folder and the copy is re-validated against the build, so a rebuild
    can never leave an earlier PDF of the same name in the client's folder.
    """
    run_dir = Path(run_dir).resolve()
    try:
        sets = discover(run_dir, stage, expect)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    review = run_dir / REVIEW_DIR
    review.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    for template, category, name, images in sets:
        manifest = review / (name[:-4] + ".order.json")
        manifest.write_text(json.dumps({
            "category": category,
            "output": name,
            "pages": [{"path": os.path.relpath(p, review), "label": part_label(i)}
                      for i, p in enumerate(images, start=1)],
        }, indent=2), encoding="utf-8")
        dest = Path(deliver).resolve() / name if deliver else None

        def run(script, *extra):
            proc = subprocess.run([sys.executable, str(here / script), str(manifest), *extra],
                                  capture_output=True, text=True)
            print((proc.stdout + proc.stderr).strip())
            if proc.returncode != 0:
                for stale in (review / name, review / (name + ".manifest.json"), dest):
                    if stale:
                        stale.unlink(missing_ok=True)
                print(f"FAIL: {stage} {name} did not pass {script}; the PDF was removed.")
            return proc.returncode

        if run("combine_review_pdf.py", "--overwrite") or run("validate_review_pdf.py"):
            return 1
        if dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(review / name, dest)
            if run("validate_review_pdf.py", "--delivered-pdf", str(dest)):
                return 1
        if stage in CONTRACT_COPY:
            shutil.copyfile(review / name, run_dir / stage / CONTRACT_COPY[stage])
    return 0


def main():
    parser = argparse.ArgumentParser(description="Combine an explicit ordered BlackCEO wireframe/mockup image set into a review PDF.")
    parser.add_argument("manifest", type=Path, help="an order manifest, or a run dir with --stage")
    parser.add_argument("--stage", choices=sorted(STAGE_PDFS),
                        help="treat the first argument as a run dir: combine and validate that stage's desktop/mobile review PDFs")
    parser.add_argument("--expect", type=int, default=None, help="with --stage: the expected section count")
    parser.add_argument("--deliver", type=Path, help="with --stage: also copy each validated PDF into this client folder and prove the copy is the build")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resolution", type=float, default=144.0)
    args = parser.parse_args()
    if args.stage:
        return build_stage(args.manifest, args.stage, args.expect, args.deliver)

    try:
        from PIL import Image
    except ImportError:
        print("FAIL: Pillow is required. Install the Python package 'Pillow' in this runtime.")
        return 2

    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read manifest: {exc}")
        return 2

    category = data.get("category")
    pages = data.get("pages")
    output_name = data.get("output")
    errors = []
    if category not in ALLOWED:
        errors.append(f"category must be one of: {', '.join(sorted(ALLOWED))}")
    if not isinstance(pages, list) or not pages:
        errors.append("pages must be a non-empty ordered array.")
    if not isinstance(output_name, str) or not output_name.lower().endswith(".pdf"):
        errors.append("output must be a PDF filename/path.")
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    base = args.manifest.parent
    resolved = []
    for i, item in enumerate(pages, start=1):
        if not isinstance(item, dict) or not item.get("path"):
            errors.append(f"pages[{i}] must contain path.")
            continue
        path = (base / item["path"]).resolve()
        if not path.exists():
            errors.append(f"Missing page {i}: {path}")
            continue
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            errors.append(f"Unsupported page image type: {path}")
        errors.extend(check_name(category, path))
        resolved.append((path, item.get("label", f"Page {i}")))

    if len({str(p) for p, _ in resolved}) != len(resolved):
        errors.append("The ordered page list contains duplicate image paths.")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    output = (base / output_name).resolve() if not Path(output_name).is_absolute() else Path(output_name).resolve()
    if output.exists() and not args.overwrite:
        print(f"FAIL: output already exists: {output}. Use --overwrite to replace it.")
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)

    pil_pages = []
    try:
        for path, _ in resolved:
            im = Image.open(path)
            if im.mode in {"RGBA", "LA"}:
                bg = Image.new("RGB", im.size, "white")
                alpha = im.getchannel("A") if im.mode == "RGBA" else im.getchannel("A")
                bg.paste(im.convert("RGB"), mask=alpha)
                im = bg
            else:
                im = im.convert("RGB")
            pil_pages.append(im.copy())
            im.close()
        first, rest = pil_pages[0], pil_pages[1:]
        # quality 95, no chroma subsampling: small printed text must stay legible.
        first.save(output, "PDF", save_all=True, append_images=rest, resolution=args.resolution,
                   quality=95, subsampling=0)
    finally:
        for im in pil_pages:
            try:
                im.close()
            except Exception:
                pass

    receipt = {
        "category": category,
        "pdf": str(output),
        "page_count": len(resolved),
        "pages": [
            {"order": i, "label": label, "path": str(path), "sha256": sha256(path)}
            for i, (path, label) in enumerate(resolved, start=1)
        ],
        "pdf_sha256": sha256(output),
    }
    receipt_path = output.with_suffix(output.suffix + ".manifest.json")
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print(f"PASS: created {output} with {len(resolved)} pages.")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
