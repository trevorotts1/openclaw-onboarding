#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_pages(pdf_path):
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        data = pdf_path.read_bytes()
        return len(re.findall(rb"/Type\s*/Page(?!s)\b", data))


def page_sizes(pdf_path):
    """(width, height) in points of every page, in page order."""
    try:
        from pypdf import PdfReader
        return [(float(pg.mediabox.width), float(pg.mediabox.height)) for pg in PdfReader(str(pdf_path)).pages]
    except Exception:
        # Pillow writes plain-text page objects, so the MediaBox is greppable.
        data = pdf_path.read_bytes()
        return [(float(w), float(h)) for w, h in
                re.findall(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", data)]


def check_geometry(pdf_path, image_paths):
    """One page width for the whole set, and each page the same shape as its
    source image: nothing cropped, stretched, padded or overlapped."""
    from PIL import Image
    errors = []
    sizes = page_sizes(pdf_path)
    if len(sizes) != len(image_paths):
        return [f"PDF page sizes could not be read for all {len(image_paths)} pages (got {len(sizes)})."]
    if max(w for w, _ in sizes) - min(w for w, _ in sizes) > 0.5:
        errors.append(f"Pages have different widths {sorted({round(w, 1) for w, _ in sizes})}; a top-to-bottom set has one page width.")
    for i, ((w, h), path) in enumerate(zip(sizes, image_paths), start=1):
        with Image.open(path) as im:
            iw, ih = im.size
        if abs(w / h - iw / ih) / (iw / ih) > 0.005:
            errors.append(f"Page {i} is {w:.0f}x{h:.0f}pt but its source image is {iw}x{ih}px: the page was cropped, stretched or padded.")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate a BlackCEO review PDF against its ordered manifest and receipt.")
    parser.add_argument("manifest", type=Path, help="an order manifest, or a run dir with --stage")
    parser.add_argument("pdf", nargs="?", type=Path)
    parser.add_argument("--stage", help="treat the first argument as a run dir and validate that stage's review PDFs")
    args = parser.parse_args()
    if args.stage:
        return validate_stage(args.manifest, args.stage)
    return validate(args.manifest, args.pdf)


def validate(manifest_path, pdf_arg=None):
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read manifest: {exc}")
        return 2

    output_name = manifest.get("output")
    if pdf_arg:
        pdf_path = pdf_arg.resolve()
    elif isinstance(output_name, str):
        pdf_path = (manifest_path.parent / output_name).resolve()
    else:
        print("FAIL: no PDF path supplied and manifest.output is missing.")
        return 1

    receipt_path = pdf_path.with_suffix(pdf_path.suffix + ".manifest.json")
    errors = []
    if not pdf_path.exists():
        errors.append(f"PDF does not exist: {pdf_path}")
    if not receipt_path.exists():
        errors.append(f"Receipt does not exist: {receipt_path}")
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read receipt: {exc}")
        return 2

    expected_pages = manifest.get("pages", [])
    if receipt.get("page_count") != len(expected_pages):
        errors.append("Receipt page_count does not match manifest page list.")
    actual_count = count_pages(pdf_path)
    if actual_count != len(expected_pages):
        errors.append(f"PDF has {actual_count} pages; manifest expects {len(expected_pages)}.")
    if receipt.get("pdf_sha256") != sha256(pdf_path):
        errors.append("PDF hash does not match receipt.")

    receipt_pages = receipt.get("pages", [])
    if len(receipt_pages) != len(expected_pages):
        errors.append("Receipt page list length does not match manifest.")
    else:
        for i, (expected, got) in enumerate(zip(expected_pages, receipt_pages), start=1):
            expected_path = (manifest_path.parent / expected.get("path", "")).resolve()
            if not expected_path.exists():
                errors.append(f"Source page {i} is missing: {expected_path}")
                continue
            if Path(got.get("path", "")).resolve() != expected_path:
                errors.append(f"Receipt path mismatch at page {i}.")
            if got.get("sha256") != sha256(expected_path):
                errors.append(f"Source image hash mismatch at page {i}.")
            if got.get("order") != i:
                errors.append(f"Receipt order mismatch at page {i}.")

    if not errors:
        try:
            errors.extend(check_geometry(pdf_path, [(manifest_path.parent / e["path"]).resolve() for e in expected_pages]))
        except ImportError:
            errors.append("Pillow is required to check page geometry.")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS: {pdf_path.name} has {actual_count} pages in the declared order.")
    return 0


def validate_stage(run_dir, stage):
    """Gate form: every review PDF the stage owes exists, is in section order,
    and matches the stage's real section images."""
    import combine_review_pdf as crp
    run_dir = Path(run_dir).resolve()
    try:
        sets = crp.discover(run_dir, stage)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    rc = 0
    for _template, _category, name, images in sets:
        manifest = run_dir / crp.REVIEW_DIR / (name[:-4] + ".order.json")
        if not manifest.exists():
            print(f"FAIL: {stage}: review PDF {name} was never built (no {manifest.name}); run combine_review_pdf.py --stage")
            rc = 1
            continue
        want = [(manifest.parent / p["path"]).resolve() for p in json.loads(manifest.read_text(encoding="utf-8"))["pages"]]
        if want != [p.resolve() for p in images]:
            print(f"FAIL: {stage}: {name} was built from a different image list than the stage now holds (rebuild it).")
            rc = 1
            continue
        rc = max(rc, validate(manifest))
    return rc


if __name__ == "__main__":
    sys.exit(main())
