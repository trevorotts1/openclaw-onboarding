#!/usr/bin/env python3
"""Deterministically compose the Skill 71 hybrid board (Update Plan Item 12).

Usage:
  python3 scripts/build_hybrid_board.py <run_dir> [--record NAME] [--overwrite]

The hybrid board is the standard deliverable at mockup approval: one
sheet, three panels (trait H1 of the Item 14 trait checklist) - the
mockup-fidelity desktop page, the section guide column, and the
mockup-fidelity mobile page - so structure and finished look are
approved from a single sheet. The board is composed by this code, never
by an agent's hand and never by a new generation pass, from the
already-approved section artifacts named by the board record
(`final-mockups/hybrid-board.json`, validated by
scripts/validate_hybrid_board.py):

  - the desktop panel is the approved desktop mockup artifact itself,
    scaled to the panel width, byte-pinned by its recorded sha256;
  - the mobile panel is the approved mobile mockup artifact itself,
    likewise;
  - the guide column is drawn from the record's guide: for each
    section, in order, its number and name, its mini wireframe
    thumbnail (the approved desktop wireframe slice, scaled down), and
    its typography specs (trait H2: the guide matches the mockups).

The composer refuses to build from a record that does not pass
validation, so a board can never be composed from artifacts other than
the approved ones the record names. On success it writes the board PNG
(the record's `board_output`, default `final-mockups/hybrid-board.png`)
and `final-mockups/hybrid-board-receipt.json` with the sha256 of every
input, the board's own sha256, and the panel geometry. The board is the
artifact the final-mockups stage's approval is recorded against.

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import argparse
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_hybrid_board as vhb  # noqa: E402

MARGIN = 24
GAP = 24
HEADER_H = 40
DESKTOP_W = 720
GUIDE_W = 400
MOBILE_W = 280
SECTION_GAP = 16
LINE_H = 18
THUMB_GAP = 6


def _font(size=14):
    try:
        from PIL import ImageFont
        return ImageFont.load_default(size=size)
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def _scaled(im, width):
    if im.width == width:
        return im
    height = max(1, round(im.height * width / im.width))
    return im.resize((width, height))


def _wrap(text, width_chars):
    return textwrap.wrap(str(text), width=width_chars) or [""]


def main():
    parser = argparse.ArgumentParser(
        description="Compose the hybrid board from the approved artifacts named by the board record.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--record", default="hybrid-board.json",
                        help="Board record filename inside final-mockups/ (default hybrid-board.json).")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    run_dir = args.run_dir
    stage_dir = run_dir / "final-mockups"
    record_path = stage_dir / args.record
    try:
        data = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read hybrid board record: {exc}")
        return 2

    failures = vhb.check_board(data, run_dir=run_dir)
    if failures:
        print("FAIL: refusing to compose the board; the board record does not pass:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("FAIL: Pillow is required. Install the Python package 'Pillow' in this runtime.")
        return 2

    output_name = data.get("board_output", "hybrid-board.png")
    output = stage_dir / output_name
    if output.exists() and not args.overwrite:
        print(f"FAIL: output already exists: {output}. Use --overwrite to replace it.")
        return 1

    def load(rel):
        with Image.open(run_dir / rel) as im:
            return im.convert("RGB")

    desktop = _scaled(load(data["desktop_panel"]["source"]), DESKTOP_W)
    mobile = _scaled(load(data["mobile_panel"]["source"]), MOBILE_W)

    guide = data["guide"]
    font = _font(14)
    header_font = _font(16)
    chars = max(10, GUIDE_W // 8)
    guide_blocks = []
    guide_height = 0
    for section in guide["sections"]:
        thumb = _scaled(load(section["wireframe_thumbnail"]), GUIDE_W)
        specs = section["type_specs"]
        lines = [f"{section['number']}. {section['name']}"]
        lines += _wrap(f"Heading: {specs['heading']}", chars)
        lines += _wrap(f"Body: {specs['body']}", chars)
        lines += _wrap(f"CTA: {specs['cta']}", chars)
        block_height = thumb.height + THUMB_GAP + LINE_H * len(lines)
        guide_blocks.append((thumb, lines, block_height))
        guide_height += block_height + SECTION_GAP
    guide_height -= SECTION_GAP

    body_height = max(desktop.height, mobile.height, guide_height)
    sheet_w = MARGIN * 2 + DESKTOP_W + GAP + GUIDE_W + GAP + MOBILE_W
    sheet_h = MARGIN * 2 + HEADER_H + body_height
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)

    panels = [
        ("desktop", MARGIN, DESKTOP_W, "DESKTOP MOCKUP"),
        ("guide", MARGIN + DESKTOP_W + GAP, GUIDE_W, "SECTION GUIDE"),
        ("mobile", MARGIN + DESKTOP_W + GAP + GUIDE_W + GAP, MOBILE_W, "MOBILE MOCKUP"),
    ]
    geometry = {}
    for name, x, width, title in panels:
        draw.rectangle([x, MARGIN, x + width, MARGIN + HEADER_H - 4], fill=(24, 24, 24))
        draw.text((x + 8, MARGIN + 10), title, fill="white", font=header_font)
        geometry[name] = {"x": x, "y": MARGIN + HEADER_H, "width": width}
    top = MARGIN + HEADER_H
    sheet.paste(desktop, (geometry["desktop"]["x"], top))
    geometry["desktop"]["height"] = desktop.height
    sheet.paste(mobile, (geometry["mobile"]["x"], top))
    geometry["mobile"]["height"] = mobile.height
    gx = geometry["guide"]["x"]
    y = top
    for thumb, lines, block_height in guide_blocks:
        sheet.paste(thumb, (gx, y))
        ty = y + thumb.height + THUMB_GAP
        for line in lines:
            draw.text((gx, ty), line, fill="black", font=font)
            ty += LINE_H
        y += block_height + SECTION_GAP
    geometry["guide"]["height"] = guide_height

    sheet.save(output, "PNG")

    inputs = []
    for key in ("desktop_panel", "mobile_panel"):
        panel = data[key]
        inputs.append({"source": panel["source"], "sha256": panel["sha256"]})
    for section in guide["sections"]:
        inputs.append({"source": section["wireframe_thumbnail"],
                       "sha256": section["sha256"]})
    receipt = {
        "board_output": output_name,
        "sheet": {"width": sheet_w, "height": sheet_h},
        "panels": geometry,
        "inputs": inputs,
        "output_sha256": vhb.sha256(output),
    }
    receipt_path = stage_dir / "hybrid-board-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print(f"PASS: composed the hybrid board ({sheet_w}x{sheet_h}) from "
          f"{len(inputs)} approved input artifact(s) into {output}.")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
