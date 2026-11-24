#!/usr/bin/env python3
"""Deterministically compose the Skill 71 hybrid board (Update Plan Item 12).

Usage:
  python3 scripts/build_hybrid_board.py <run_dir> [--record NAME] [--overwrite] [--refresh-record]

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

--refresh-record re-pins the board record's two panels to the CURRENT approved
full mockups before composing, because no other tool rewrites hybrid-board.json
and a re-stitched mockup leaves the old pin stale. The desktop panel is the
desktop stitch (final-mockups/<stitched_output>), the mobile panel is the mobile
stitch (final-mockups/mobile/<stitched_output>); both paths come from the
production records and the stitch receipts beside them, never from a guess.
It VERIFIES first and refuses on any mismatch, writing nothing: per viewport the
production record exists and passes validate_production_record, the stitch receipt
names the record's stitched output, the panel file hashes (freshly read) to the
receipt's output_sha256, every slice the receipt lists is on disk, hashes to the
receipt's sha256, is the record's section in order, and equals the sha256 the
export receipt (export_native_slices.py, re-verified file by file) holds for it,
and the record's own export.receipt_sha256 equals the re-verified export receipt's.
No hash a record claims about itself is trusted. Then it writes the new record
with a `refreshed_from` provenance block (prior and new panel paths and shas, the
receipts relied on with their file hashes, and `receipt_sha256` over the block's
content), validates it, and only then composes the board (--overwrite semantics
unchanged: it refuses before writing when the board exists without --overwrite).
Without the flag nothing changes.

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import argparse
import hashlib
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_hybrid_board as vhb  # noqa: E402
import stitch_sections as ss  # noqa: E402
import validate_production_record as vpr  # noqa: E402

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


STAGE = "final-mockups"
VIEWPORT_DIRS = {"desktop": STAGE, "mobile": f"{STAGE}/mobile"}
EXPORT_RECEIPT = "export-receipt.json"
STITCH_RECEIPT = "stitch-receipt.json"


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, f"{path} is missing or unreadable ({type(exc).__name__})"


def _verify_viewport(run_dir, viewport, export_rows, export_receipt_hash):
    """Everything one panel must prove. Returns (failures, info)."""
    rel_dir = VIEWPORT_DIRS[viewport]
    vp_dir = Path(run_dir) / rel_dir
    fails = []
    record_path = vp_dir / "production-record.json"
    record, err = _read_json(record_path)
    if err:
        return [f"{viewport}: the production record {err}"], None
    bad = vpr.check_record(record, base_dir=vp_dir)
    if bad:
        return [f"{viewport}: the production record does not pass validate_production_record: {b}" for b in bad], None
    stitched = record.get("stitched_output")
    if not isinstance(stitched, str) or not stitched or "/" in stitched:
        return [f"{viewport}: the production record names no stitched_output"], None
    receipt_path = vp_dir / STITCH_RECEIPT
    receipt, err = _read_json(receipt_path)
    if err:
        return [f"{viewport}: the stitch receipt {err}"], None
    if receipt.get("stitched_output") != stitched:
        fails.append(f"{viewport}: the stitch receipt names {receipt.get('stitched_output')!r}, "
                     f"the production record names {stitched!r}")
    panel = vp_dir / stitched
    if not panel.is_file():
        fails.append(f"{viewport}: the panel file {rel_dir}/{stitched} is not on disk")
        return fails, None
    panel_sha = vhb.sha256(panel)
    if panel_sha != receipt.get("output_sha256"):
        fails.append(f"{viewport}: the panel file {rel_dir}/{stitched} hashes to {panel_sha[:12]} but its stitch "
                     f"receipt records {str(receipt.get('output_sha256'))[:12]}; it is not the stitch the receipt made")
    rec_sections, rcp_sections = record["sections"], receipt.get("sections")
    if not isinstance(rcp_sections, list) or len(rcp_sections) != len(rec_sections):
        fails.append(f"{viewport}: the stitch receipt lists "
                     f"{len(rcp_sections) if isinstance(rcp_sections, list) else 'no'} section(s), the production "
                     f"record {len(rec_sections)}")
        return fails, None
    for number, (rec, rcp) in enumerate(zip(rec_sections, rcp_sections), start=1):
        label = f"{viewport}/{rec.get('slice')}"
        if rcp.get("slice") != rec.get("slice") or str(rcp.get("section_id")) != str(rec.get("section_id")) \
                or rcp.get("order") != number:
            fails.append(f"{label}: the stitch receipt's section {number} is {rcp.get('slice')!r}, not the "
                         f"production record's, in order")
            continue
        path = vp_dir / rcp["slice"]
        if not path.is_file():
            fails.append(f"{label}: the slice the stitch receipt lists is not on disk")
            continue
        current = vhb.sha256(path)
        if current != rcp.get("sha256"):
            fails.append(f"{label}: the slice hashes to {current[:12]} now but the stitch receipt records "
                         f"{str(rcp.get('sha256'))[:12]}; the panel was stitched from other slices")
        row = export_rows.get((viewport, Path(rcp["slice"]).name))
        if row is None:
            fails.append(f"{label}: the export receipt has no row for this slice")
            continue
        if row["output"].get("path") != f"{viewport}/{Path(rcp['slice']).name}":
            fails.append(f"{label}: the export receipt's output path {row['output'].get('path')!r} is not this slice")
        if row["output"].get("sha256") != rcp.get("sha256"):
            fails.append(f"{label}: the stitch receipt's input {str(rcp.get('sha256'))[:12]} is not the slice the "
                         f"export receipt holds ({str(row['output'].get('sha256'))[:12]}); the stitch is not of the "
                         f"current export")
        claimed = (rec.get("export") or {}).get("receipt_sha256")
        if claimed != export_receipt_hash:
            fails.append(f"{label}: the production record cites export receipt {str(claimed)[:12]}, the verified "
                         f"export receipt is {export_receipt_hash[:12]}; the record is stale")
    if fails:
        return fails, None
    fails = _recompute_panel(vp_dir, viewport, record, receipt, panel, rel_dir, stitched)
    if fails:
        return fails, None
    return [], {
        "panel": {"source": f"{rel_dir}/{stitched}", "sha256": panel_sha},
        "stitch_receipt": {"path": f"{rel_dir}/{STITCH_RECEIPT}", "file_sha256": vhb.sha256(receipt_path),
                           "output_sha256": receipt["output_sha256"]},
        "production_record": {"path": f"{rel_dir}/production-record.json", "file_sha256": vhb.sha256(record_path)},
    }


def _recompute_panel(vp_dir, viewport, record, receipt, panel, rel_dir, stitched):
    """Recompute the panel from the verified slices with stitch_sections' own function and require the
    panel file to be that image. A stitch receipt is a claim; this is the proof. Returns failures."""
    try:
        from PIL import Image
    except ImportError:
        return [f"{viewport}: Pillow is required to recompute the panel from its slices"]
    sections = record["sections"]
    widths = {s["width"] for s in sections}
    if len(widths) != 1:
        return [f"{viewport}: the production record's section widths differ ({sorted(widths)}); no single page width"]
    page_width = widths.pop()
    try:
        canvas, rebuilt = ss.compose_canvas(vp_dir, sections, page_width)
    except Exception as exc:
        return [f"{viewport}: the panel could not be recomputed from its slices ({type(exc).__name__}: {exc})"]
    fails = []
    for key, value in (("page_width", page_width), ("total_height", canvas.height)):
        if receipt.get(key) != value:
            fails.append(f"{viewport}: the stitch receipt's {key} is {receipt.get(key)!r}, the slices make {value}")
    for mine, theirs in zip(rebuilt, receipt["sections"]):
        for key in ("width", "height", "y_offset"):
            if theirs.get(key) != mine[key]:
                fails.append(f"{viewport}/{mine['slice']}: the stitch receipt's {key} is {theirs.get(key)!r}, "
                             f"the recomputed stitch has {mine[key]!r}")
    try:
        with Image.open(panel) as im:
            fmt = im.format
            actual = im.convert("RGB")
    except Exception as exc:
        return fails + [f"{viewport}: the panel file {rel_dir}/{stitched} is not a readable image ({type(exc).__name__})"]
    if fmt != "PNG":
        fails.append(f"{viewport}: the panel file {rel_dir}/{stitched} is {fmt}, not the PNG the stitcher writes")
    if actual.size != canvas.size:
        fails.append(f"{viewport}: the panel file {rel_dir}/{stitched} is {actual.width}x{actual.height}, the "
                     f"stitch recomputed from its verified slices is {canvas.width}x{canvas.height}; the panel is "
                     f"not the stitch of those slices")
    elif actual.tobytes() != canvas.tobytes():
        fails.append(f"{viewport}: the panel file {rel_dir}/{stitched} has different pixels from the stitch "
                     f"recomputed from its verified slices; the panel is not the stitch of those slices")
    return fails


def _provenance_hash(block):
    body = {k: v for k, v in block.items() if k != "receipt_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def refresh_record(run_dir, record_name, now=None):
    """Verify, then return (failures, new_record, prior_record_text). Writes nothing."""
    import export_native_slices as exporter
    run_dir = Path(run_dir)
    stage_dir = run_dir / STAGE
    prior, err = _read_json(stage_dir / record_name)
    if err:
        return [f"the board record {err}"], None
    if not isinstance(prior, dict):
        return ["the board record is not a JSON object"], None
    export_path = stage_dir / EXPORT_RECEIPT
    bad = exporter.verify_receipt(export_path, stage_dir)
    if bad:
        return [f"the export receipt does not verify: {b}" for b in bad], None
    export_receipt, err = _read_json(export_path)
    if err:
        return [f"the export receipt {err}"], None
    rows = {(r["viewport"], r["section_part"]): r for r in export_receipt["entries"]}
    export_hash = exporter.body_hash(export_receipt)
    failures, info = [], {}
    for viewport in ("desktop", "mobile"):
        fails, got = _verify_viewport(run_dir, viewport, rows, export_hash)
        failures.extend(fails)
        info[viewport] = got
    if failures:
        return failures, None
    new = dict(prior)
    new["desktop_panel"] = dict(info["desktop"]["panel"])
    new["mobile_panel"] = dict(info["mobile"]["panel"])
    block = {
        "tool": "build_hybrid_board.py --refresh-record",
        "refreshed_at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prior": {"desktop_panel": prior.get("desktop_panel"), "mobile_panel": prior.get("mobile_panel")},
        "new": {"desktop_panel": new["desktop_panel"], "mobile_panel": new["mobile_panel"]},
        "receipts": {
            "export": {"path": f"{STAGE}/{EXPORT_RECEIPT}", "receipt_sha256": export_hash,
                       "file_sha256": vhb.sha256(export_path)},
            "desktop": {"stitch_receipt": info["desktop"]["stitch_receipt"],
                        "production_record": info["desktop"]["production_record"]},
            "mobile": {"stitch_receipt": info["mobile"]["stitch_receipt"],
                       "production_record": info["mobile"]["production_record"]},
        },
    }
    block["receipt_sha256"] = _provenance_hash(block)
    new["refreshed_from"] = block
    bad = vhb.check_board(new, run_dir=run_dir)
    if bad:
        return [f"the refreshed record does not pass validate_hybrid_board: {b}" for b in bad], None
    return [], new


def main():
    parser = argparse.ArgumentParser(
        description="Compose the hybrid board from the approved artifacts named by the board record.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--record", default="hybrid-board.json",
                        help="Board record filename inside final-mockups/ (default hybrid-board.json).")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--refresh-record", action="store_true",
                        help="Verify the current stitched mockups against their receipts and re-pin the record's "
                             "desktop and mobile panels to them (writes the record with refreshed_from provenance) "
                             "before composing.")
    args = parser.parse_args()

    run_dir = args.run_dir
    stage_dir = run_dir / "final-mockups"
    record_path = stage_dir / args.record
    if args.refresh_record:
        failures, new = refresh_record(run_dir, args.record)
        if failures:
            print("FAIL: refusing to refresh the board record; nothing was written:")
            for failure in failures:
                print(f"- {failure}")
            return 1
        # The record is written only after the board composes; a compose failure leaves the prior record
        # byte for byte (nothing was touched until then, and the write below is an atomic replace).
        board_path = stage_dir / new.get("board_output", "hybrid-board.png")
        board_receipt = stage_dir / "hybrid-board-receipt.json"
        fresh = [q for q in (board_path, board_receipt) if not q.exists()]
        try:
            rc = compose_board(run_dir, new, args.overwrite,
                               refusal_note="the record was not rewritten.")
        except Exception as exc:
            for q in fresh:  # remove only what this run created; the prior record is untouched
                q.unlink(missing_ok=True)
            print(f"FAIL: the board could not be composed ({type(exc).__name__}: {exc}); "
                  "the record was not rewritten.")
            return 1
        if rc != 0:
            return rc
        tmp = record_path.with_name(f".{record_path.name}.refresh.tmp")
        tmp.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, record_path)
        print(f"PASS: re-pinned {record_path.name}: desktop {new['desktop_panel']['source']} "
              f"{new['desktop_panel']['sha256'][:12]}, mobile {new['mobile_panel']['source']} "
              f"{new['mobile_panel']['sha256'][:12]} (provenance {new['refreshed_from']['receipt_sha256'][:12]}).")
        return 0
    try:
        data = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read hybrid board record: {exc}")
        return 2
    return compose_board(run_dir, data, args.overwrite)


def compose_board(run_dir, data, overwrite, refusal_note=""):
    """Compose the board from a record dict. Writes the board and its receipt only; never the record."""
    stage_dir = Path(run_dir) / "final-mockups"
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
    if output.exists() and not overwrite:
        print(f"FAIL: output already exists: {output}. Use --overwrite to replace it"
              + (f"; {refusal_note}" if refusal_note else "."))
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
