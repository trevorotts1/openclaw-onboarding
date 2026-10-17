#!/usr/bin/env python3
"""Deterministically stitch Skill 71 section slices into the full-page PNG.

Usage:
  python3 scripts/stitch_sections.py <stage_dir> [--record NAME] [--output NAME]

The stitcher is a pinned step of the Item 13 production method: section
images are assembled by this code, never by an agent's hand. It reads the
stage folder's production record (default `production-record.json`), runs
the full production-record check (generation inputs, native-aspect output,
and the per-section text-QC leg, via validate_production_record.py), and
refuses to stitch when any section fails: a garbled or un-QC'd section is
never accepted into the combined artifact. On success it pastes the
slices vertically, in record order, onto one full-page PNG (the record's
`stitched_output`, default `wireframe-full.png`) and writes
`stitch-receipt.json` beside it with the section order and the SHA-256 of
every slice and of the stitched output.

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_production_record as vpr  # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Stitch the ordered section slices named by a production record into one full-page PNG.")
    parser.add_argument("stage_dir", type=Path)
    parser.add_argument("--record", default="production-record.json")
    parser.add_argument("--output", default=None,
                        help="Stitched PNG filename (default: the record's stitched_output, else wireframe-full.png).")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    stage_dir = args.stage_dir
    record_path = stage_dir / args.record
    try:
        data = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read production record: {exc}")
        return 2

    failures = vpr.check_record(data, base_dir=stage_dir)
    if failures:
        print("FAIL: refusing to stitch; the production record does not pass:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    sections = data["sections"]
    widths = {s["width"] for s in sections}
    if len(widths) != 1:
        print("FAIL: refusing to stitch; section widths differ "
              f"({sorted(widths)}); a full-page sheet has one page width.")
        return 1
    page_width = widths.pop()
    if isinstance(data.get("page_width"), int) and data["page_width"] != page_width:
        print(f"FAIL: record page_width {data['page_width']} does not match the section width {page_width}.")
        return 1

    try:
        from PIL import Image
    except ImportError:
        print("FAIL: Pillow is required. Install the Python package 'Pillow' in this runtime.")
        return 2

    output_name = args.output or data.get("stitched_output") or "wireframe-full.png"
    output = stage_dir / output_name
    if output.exists() and not args.overwrite:
        print(f"FAIL: output already exists: {output}. Use --overwrite to replace it.")
        return 1

    total_height = sum(s["height"] for s in sections)
    canvas = Image.new("RGB", (page_width, total_height), "white")
    receipt_sections = []
    y = 0
    for i, section in enumerate(sections, start=1):
        slice_path = stage_dir / section["slice"]
        with Image.open(slice_path) as im:
            canvas.paste(im.convert("RGB"), (0, y))
        receipt_sections.append({
            "order": i,
            "section_id": section["section_id"],
            "slice": section["slice"],
            "sha256": sha256(slice_path),
            "width": section["width"],
            "height": section["height"],
            "y_offset": y,
        })
        y += section["height"]
    canvas.save(output, "PNG")

    receipt = {
        "stitched_output": output_name,
        "page_width": page_width,
        "total_height": total_height,
        "section_count": len(sections),
        "sections": receipt_sections,
        "output_sha256": sha256(output),
    }
    receipt_path = stage_dir / "stitch-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print(f"PASS: stitched {len(sections)} section(s) in record order into {output} "
          f"({page_width}x{total_height}).")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
