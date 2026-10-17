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

Item 16 structural drift pass: when both HTML sources exist
(<run_dir>/final-mockups/mockup.html and <run_dir>/responsive-html/
index.html), both are rendered at 1440 and 390 and their section sequences
are compared with validate_page.py's signature function (one implementation,
two callers): section count, section order, per-section image-placement
class, and heading-to-body font-size ratios (15% drift tolerance). The
per-section drift table lands in
<run_dir>/responsive-html/compare/compare-report.json; drift failures print
as named DRIFT lines and exit 1. When either HTML source is absent the
drift pass records status "skipped-no-html" and the sheet behavior is
unchanged. When the HTML sources exist but Playwright is unavailable, the
pass records "unavailable-playwright" and exits 2 (the drift floor cannot
be verified, so the stage must not close on sheets alone).

Exit codes: 0 ok; 1 missing input or structural drift; 2 unreadable input
or drift pass unavailable.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from validate_page import (  # noqa: E402
        LAYOUT_JS,
        heading_body_ratio,
        image_placement_class,
        section_signature,
    )
except Exception:  # pragma: no cover - validate_page always ships alongside
    LAYOUT_JS = None
    heading_body_ratio = None
    image_placement_class = None
    section_signature = None

GAP = 24
LABEL_BAR_HEIGHT = 40
MAX_SHEET_HEIGHT = 3000
HEADING_RATIO_TOLERANCE = 0.15
DRIFT_WIDTHS = (1440, 390)

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


def compare_section_structures(mockup_sections, page_sections,
                               tolerance=HEADING_RATIO_TOLERANCE):
    """Pure drift comparison (unit-testable without a browser). Takes the
    LAYOUT_JS section dicts for mockup and page at one width; returns
    (failures, table). Failures are named DRIFT lines; the table carries
    one row per section index with both signatures, both image-placement
    classes, both heading-to-body ratios, and the row's failures."""
    failures = []
    table = []
    if section_signature is None:
        return ["validate_page signature import unavailable"], table
    m_sigs = [section_signature(s) for s in mockup_sections]
    p_sigs = [section_signature(s) for s in page_sections]
    if len(m_sigs) != len(p_sigs):
        failures.append(
            "DRIFT: section count differs: mockup has {} sections, page "
            "has {}".format(len(m_sigs), len(p_sigs)))
    elif m_sigs != p_sigs:
        first = next(i for i, (a, b) in enumerate(zip(m_sigs, p_sigs))
                     if a != b)
        failures.append(
            "DRIFT: section order differs: first mismatch at section {} "
            "(mockup {} vs page {})".format(first + 1, m_sigs[first],
                                            p_sigs[first]))
    for i in range(min(len(mockup_sections), len(page_sections))):
        m, p = mockup_sections[i], page_sections[i]
        row = {
            "section": i + 1,
            "mockup_signature": m_sigs[i],
            "page_signature": p_sigs[i],
            "mockup_image_placement": image_placement_class(m),
            "page_image_placement": image_placement_class(p),
            "mockup_heading_body_ratio": heading_body_ratio(m),
            "page_heading_body_ratio": heading_body_ratio(p),
            "failures": [],
        }
        if row["mockup_image_placement"] != row["page_image_placement"]:
            row["failures"].append(
                "DRIFT: section {} image placement changed: mockup {} "
                "vs page {}".format(i + 1, row["mockup_image_placement"],
                                    row["page_image_placement"]))
        mr, pr = row["mockup_heading_body_ratio"], row["page_heading_body_ratio"]
        if mr and pr:
            drift = abs(pr - mr) / mr
            row["heading_ratio_drift"] = round(drift, 4)
            if drift > tolerance:
                row["failures"].append(
                    "DRIFT: section {} heading-to-body font-size ratio "
                    "drifted {:.0%}: mockup {:.2f} vs page {:.2f} "
                    "(tolerance {:.0%})".format(i + 1, drift, mr, pr,
                                                tolerance))
        row["status"] = "drift" if row["failures"] else "ok"
        failures.extend(row["failures"])
        table.append(row)
    return failures, table


def extract_sections(html_path, width):
    """Render one HTML file at one width and return its LAYOUT_JS section
    list. Requires Playwright; raises RuntimeError when unavailable."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(f"Playwright unavailable: {exc}")
    import shutil
    import tempfile

    udd = tempfile.mkdtemp(prefix="skill71-compare-")
    context = None
    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                udd, headless=True,
                viewport={"width": width, "height": 800})
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(Path(html_path).resolve().as_uri(),
                      wait_until="load", timeout=30000)
            page.evaluate(
                "() => { document.querySelectorAll('img').forEach("
                "i => { i.loading = 'eager'; }); }")
            page.evaluate(
                "() => new Promise(resolve => { let y = 0; const step = "
                "() => { window.scrollTo(0, y); y += 400; "
                "if (y <= document.body.scrollHeight + 800) "
                "{ setTimeout(step, 40); } else { window.scrollTo(0, 0); "
                "setTimeout(resolve, 120); } }; step(); })")
            data = page.evaluate(LAYOUT_JS)
            return data.get("sections") or []
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        shutil.rmtree(udd, ignore_errors=True)


def run_drift_pass(run_dir):
    """Item 16: returns (status, exit_code, report_fragment). Status is
    skipped-no-html, unavailable-playwright, pass, or fail."""
    mockup_html = run_dir / "final-mockups" / "mockup.html"
    page_html = run_dir / "responsive-html" / "index.html"
    if not mockup_html.is_file() or not page_html.is_file():
        return "skipped-no-html", 0, {"status": "skipped-no-html"}
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("DRIFT CHECK UNAVAILABLE: Playwright is not installed; the "
              "structural drift pass cannot run and responsive-html must "
              "not close on compare sheets alone")
        return "unavailable-playwright", 2, {"status": "unavailable-playwright"}
    fragment = {"status": "pass", "widths": {}}
    all_failures = []
    for width in DRIFT_WIDTHS:
        try:
            mockup_sections = extract_sections(mockup_html, width)
            page_sections = extract_sections(page_html, width)
        except RuntimeError as exc:
            print(f"DRIFT CHECK UNAVAILABLE: {exc}")
            return "unavailable-playwright", 2, {
                "status": "unavailable-playwright"}
        failures, table = compare_section_structures(
            mockup_sections, page_sections)
        fragment["widths"][str(width)] = {
            "mockup_sections": len(mockup_sections),
            "page_sections": len(page_sections),
            "failures": failures,
            "table": table,
        }
        for line in failures:
            all_failures.append(f"[{width}px] {line}")
    if all_failures:
        fragment["status"] = "fail"
        for line in all_failures:
            print(line)
        return "fail", 1, fragment
    print("DRIFT OK: section structure matches the final mockup at "
          "1440 and 390 (count, order, image placement, heading ratios "
          "within 15%)")
    return "pass", 0, fragment


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

    # Item 16 structural drift pass (after the sheets exist).
    drift_status, drift_exit, drift_fragment = run_drift_pass(run_dir)
    report = {
        "tool": "compare_sheet.py",
        "skill": "71-blackceo-signature-page",
        "run_dir": str(run_dir),
        "widths": widths,
        "sheet_pieces": total,
        "drift": drift_fragment,
    }
    compare_dir = run_dir / "responsive-html" / "compare"
    try:
        compare_dir.mkdir(parents=True, exist_ok=True)
        (compare_dir / "compare-report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: could not write compare-report.json: {exc}",
              file=sys.stderr)
        return 2
    if drift_exit != 0:
        return drift_exit
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