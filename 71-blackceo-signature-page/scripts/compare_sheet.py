#!/usr/bin/env python3
"""Build side-by-side mockup-vs-page compare sheets (Pillow, no browser).

compare_sheet.py <run_dir>

Inputs, both required (exit 1 naming the missing side otherwise):
  <run_dir>/final-mockups/desktop/part-*.png  -> mockup side at 1440
  <run_dir>/final-mockups/mobile/part-*.png   -> mockup side at 390
  <run_dir>/<width>.png                       -> page screenshot per width
                                                (390 and 1440 required)

Output:
  <run_dir>/responsive-html/compare/compare-<width>-NN.png
Each sheet: mockup scaled to the width on the left, page screenshot scaled to
the same width on the right, 24px gap between them, a label bar on top
"MOCKUP | PAGE | <width>". Pieces of at most 3,000px height.

Mockup part files are stitched in filename order into one tall image before
scaling. If the page screenshot is shorter than the scaled mockup, the page
side is bottom-padded with white so the two columns stay aligned per piece.

Exit codes: 0 ok; 1 missing input; 2 unreadable input.
"""
import argparse
import re
import sys
from pathlib import Path

GAP = 24
LABEL_BAR_HEIGHT = 40
MAX_SHEET_HEIGHT = 3000

PART_RE = re.compile(r"^part-(\d+)\.png$")


def list_part_files(directory):
    if not directory.is_dir():
        return []
    entries = []
    for entry in directory.iterdir():
        match = PART_RE.match(entry.name)
        if match and entry.is_file():
            entries.append((int(match.group(1)), entry))
    entries.sort()
    return [path for _, path in entries]


def stitch_parts(paths):
    from PIL import Image

    stitched = None
    for path in paths:
        im = Image.open(path)
        im.load()
        if stitched is None:
            stitched = im.convert("RGB")
            continue
        if im.width != stitched.width:
            im = im.resize((stitched.width, round(im.height * stitched.width / im.width)))
        canvas = Image.new("RGB", (stitched.width, stitched.height + im.height), "white")
        canvas.paste(stitched, (0, 0))
        canvas.paste(im.convert("RGB"), (0, stitched.height))
        stitched = canvas
    return stitched


def make_sheet(label_width, mockup, page, out_path):
    from PIL import Image, ImageDraw

    mock = mockup.resize((label_width, round(mockup.height * label_width / mockup.width)))
    pag = page.resize((label_width, round(page.height * label_width / page.width)))

    height = max(mock.height, pag.height)
    pag_padded = Image.new("RGB", (label_width, height), "white")
    pag_padded.paste(pag, (0, 0))

    sheet_width = label_width * 2 + GAP
    sheet = Image.new(
        "RGB", (sheet_width, LABEL_BAR_HEIGHT + height), "white"
    )
    draw = ImageDraw.Draw(sheet)
    label = f"MOCKUP | PAGE | {label_width}"
    draw.text((8, 12), label, fill="black")
    sheet.paste(mock, (0, LABEL_BAR_HEIGHT))
    sheet.paste(pag_padded, (label_width + GAP, LABEL_BAR_HEIGHT))

    pieces = (sheet.height + MAX_SHEET_HEIGHT - 1) // MAX_SHEET_HEIGHT
    piece_height = (sheet.height + pieces - 1) // pieces
    out_path.parent.mkdir(parents=True, exist_ok=True)
    number = 0
    top = 0
    while top < sheet.height:
        number += 1
        h = min(piece_height, sheet.height - top)
        sheet.crop((0, top, sheet.width, top + h)).save(
            out_path.parent / f"compare-{label_width}-{number:02d}.png"
        )
        top += h
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", help="run folder containing the stage outputs")
    parser.add_argument(
        "--widths",
        default="390,1440",
        help="comma-separated widths to compare (default 390,1440)",
    )
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"ERROR: run folder not found: {run_dir}", file=sys.stderr)
        return 2

    try:
        widths = [
            int(w) for w in (x.strip() for x in args.widths.split(",")) if w.strip()
        ]
        if not widths:
            raise ValueError("empty")
    except ValueError:
        print("ERROR: --widths must be comma-separated integers", file=sys.stderr)
        return 2

    missing = []
    for width in widths:
        if width == 1440 and not list_part_files(
            run_dir / "final-mockups" / "desktop"
        ):
            missing.append("final-mockups/desktop/part-*.png")
        if width == 390 and not list_part_files(
            run_dir / "final-mockups" / "mobile"
        ):
            missing.append("final-mockups/mobile/part-*.png")
        if not (run_dir / f"{width}.png").is_file():
            missing.append(f"{width}.png")
    if missing:
        for item in dict.fromkeys(missing):
            print(f"MISSING: {item}")
        return 1

    mockups = {
        1440: stitch_parts(list_part_files(run_dir / "final-mockups" / "desktop")),
        390: stitch_parts(list_part_files(run_dir / "final-mockups" / "mobile")),
    }

    total = 0
    for width in widths:
        mockup = mockups.get(width)
        if mockup is None:
            mockup = stitch_parts(
                list_part_files(run_dir / "final-mockups" / "desktop" if width > 390 else "final-mockups" / "mobile")
            )
        page = Image_open_safe(run_dir / f"{width}.png")
        if page is None:
            print(f"ERROR: cannot read {run_dir / f'{width}.png'}", file=sys.stderr)
            return 2
        count = make_sheet(
            width,
            mockup,
            page,
            run_dir / "responsive-html" / "compare" / f"compare-{width}-01.png",
        )
        print(
            f"COMPARE OK: width {width} -> {count} sheet piece(s) in "
            f"responsive-html/compare/"
        )
        total += count
    return 0


def Image_open_safe(path):
    try:
        from PIL import Image

        im = Image.open(path)
        im.load()
        return im.convert("RGB")
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())