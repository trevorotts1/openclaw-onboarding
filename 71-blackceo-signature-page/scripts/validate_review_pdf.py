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
    """THE GUARD AGAINST NOTES BETWEEN SECTIONS. A review PDF is one continuous
    page: one page width for the set; page 1 is its section image plus exactly
    ONE title band (deliverable_labels.band_height) on top; every later page is
    exactly its section image, no header, no footer, no gap. Measured in page
    geometry, so a label or notes band added anywhere else (the old header +
    footer on every page) cannot pass, whatever the manifest says."""
    from PIL import Image
    import deliverable_labels as dl
    errors = []
    sizes = page_sizes(pdf_path)
    if len(sizes) != len(image_paths):
        return [f"PDF page sizes could not be read for all {len(image_paths)} pages (got {len(sizes)})."]
    if max(w for w, _ in sizes) - min(w for w, _ in sizes) > 0.5:
        errors.append(f"Pages have different widths {sorted({round(w, 1) for w, _ in sizes})}; a top-to-bottom set has one page width.")
    for i, ((w, h), path) in enumerate(zip(sizes, image_paths), start=1):
        with Image.open(path) as im:
            iw, ih = im.size
        want = ih + (dl.band_height(iw) if i == 1 else 0)  # px; the title band exists on page 1 only
        got = h * iw / w  # page height back in source-image px
        if abs(got - want) > 2:
            what = ("an extra label or notes band (no notes between sections: the PDF reads as one continuous page, "
                    "one title band at the top of page 1 only)") if got > want + 2 else "cropped, stretched or padded"
            errors.append(f"Page {i} is {h:.0f}pt tall ({got:.0f}px at source width) but must be {want}px "
                          f"({'its section image plus the one title band' if i == 1 else 'exactly its section image'}): {what}.")
    return errors


def check_no_mid_bands(expected_pages):
    """The manifest may declare only page 1's title: a `band`, or a title on any later page, is a label band."""
    return [f"Manifest page {i} declares a label band; no notes between sections: only page 1 carries one title band."
            for i, e in enumerate(expected_pages, start=1) if "band" in e or (i > 1 and "title" in e)]


def check_delivered(sources, delivered):
    """The client's own copy of the section images (sorted *.png in `delivered`)
    must be byte-identical, page for page, to what the PDF was built from."""
    files = sorted(Path(delivered).glob("*.png"))
    if len(files) != len(sources):
        return [f"{delivered} holds {len(files)} section images; the PDF was built from {len(sources)}."]
    return [f"Page {i} was built from {src.name} ({sha256(src)[:16]}) but the delivered {f.name} is {sha256(f)[:16]}: the PDF and the delivered folder show different images."
            for i, (src, f) in enumerate(zip(sources, files), start=1) if sha256(src) != sha256(f)]


def check_delivered_pdf(pdf_path, delivered_pdf):
    """The client's copy of the PDF must be the very file the receipt
    describes (byte-identical), not an earlier build of the same name."""
    delivered_pdf = Path(delivered_pdf)
    if not delivered_pdf.is_file():
        return [f"The delivered PDF is missing: {delivered_pdf}"]
    if sha256(delivered_pdf) != sha256(pdf_path):
        return [f"The delivered {delivered_pdf.name} ({sha256(delivered_pdf)[:16]}) is not the validated build "
                f"({sha256(pdf_path)[:16]}): it is a stale or different PDF; copy the validated one over it."]
    return []


def main():
    parser = argparse.ArgumentParser(description="Validate a BlackCEO review PDF against its ordered manifest and receipt.")
    parser.add_argument("manifest", type=Path, help="an order manifest, or a run dir with --stage")
    parser.add_argument("pdf", nargs="?", type=Path)
    parser.add_argument("--delivered", type=Path, help="also require the sections in this delivered folder to be the exact images the PDF was built from")
    parser.add_argument("--delivered-pdf", type=Path, help="also require this delivered PDF to be byte-identical to the validated build")
    parser.add_argument("--delivered-pdfs", type=Path, help="with --stage: a delivered folder that must hold each of the stage's PDFs, in its category subfolder (desktop-wireframes, mobile-mockups, ...), byte-identical to the validated builds")
    parser.add_argument("--stage", help="treat the first argument as a run dir and validate that stage's review PDFs")
    args = parser.parse_args()
    if args.stage:
        return validate_stage(args.manifest, args.stage, args.delivered_pdfs)
    return validate(args.manifest, args.pdf, args.delivered, args.delivered_pdf)


def validate(manifest_path, pdf_arg=None, delivered=None, delivered_pdf=None):
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

    sources = [(manifest_path.parent / e["path"]).resolve() for e in expected_pages]
    errors.extend(check_no_mid_bands(expected_pages))
    if not errors and delivered:
        errors.extend(check_delivered(sources, delivered))
    if not errors and delivered_pdf:
        errors.extend(check_delivered_pdf(pdf_path, delivered_pdf))
    if not errors:
        try:
            errors.extend(check_geometry(pdf_path, sources))
        except ImportError:
            errors.append("Pillow is required to check page geometry.")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS: {pdf_path.name} has {actual_count} pages in the declared order.")
    return 0


def validate_stage(run_dir, stage, delivered_pdfs=None):
    """Gate form: every review PDF the stage owes exists, is in section order,
    and matches the stage's real section images; with `delivered_pdfs`, the
    client's copy of each PDF is the validated build too."""
    import combine_review_pdf as crp
    run_dir = Path(run_dir).resolve()
    try:
        sets = crp.discover(run_dir, stage)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    rc = 0
    for _template, category, name, images in sets:
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
        rc = max(rc, validate(manifest, delivered_pdf=delivered_pdfs / category / name if delivered_pdfs else None))
        copy = crp.CONTRACT_COPY.get(stage)
        if copy and rc == 0 and (run_dir / stage / copy).is_file():
            # <stage>/wireframe.pdf is the contract artifact the stage gate requires: it must be the validated build
            errs = check_delivered_pdf(manifest.parent / name, run_dir / stage / copy)
            if errs:
                print("FAIL\n- " + "\n- ".join(errs))
                rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
