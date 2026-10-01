#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


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


def main():
    parser = argparse.ArgumentParser(description="Validate a BlackCEO review PDF against its ordered manifest and receipt.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("pdf", nargs="?", type=Path)
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read manifest: {exc}")
        return 2

    output_name = manifest.get("output")
    if args.pdf:
        pdf_path = args.pdf.resolve()
    elif isinstance(output_name, str):
        pdf_path = (args.manifest.parent / output_name).resolve()
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
            expected_path = (args.manifest.parent / expected.get("path", "")).resolve()
            if not expected_path.exists():
                errors.append(f"Source page {i} is missing: {expected_path}")
                continue
            if Path(got.get("path", "")).resolve() != expected_path:
                errors.append(f"Receipt path mismatch at page {i}.")
            if got.get("sha256") != sha256(expected_path):
                errors.append(f"Source image hash mismatch at page {i}.")
            if got.get("order") != i:
                errors.append(f"Receipt order mismatch at page {i}.")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS: {pdf_path.name} has {actual_count} pages in the declared order.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
