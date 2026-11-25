#!/usr/bin/env python3
"""Validate a Skill 71 hybrid board record (Update Plan Item 12).

Usage:
  python3 scripts/validate_hybrid_board.py <run_dir> [--check-board]

The hybrid board is the standard deliverable at mockup approval: one
sheet carrying three panels (trait H1 of the Item 14 trait checklist):
the mockup-fidelity desktop page, the mockup-fidelity mobile page, and
a section guide column. The guide matches the mockups (trait H2):
numbered sections, a mini wireframe thumbnail per section, and the
section's typography specs. The board is composed deterministically by
scripts/build_hybrid_board.py from the already-approved artifacts; it
is never a new generation pass, and it is the artifact the final-mockups
stage's approval is recorded against.

The stage folder carries the board record, `final-mockups/hybrid-board.json`:

  {
    "board_output": "hybrid-board.png",
    "desktop_panel": {"source": "final-mockups/<stitched desktop mockup>",
                      "sha256": "<sha256 of that file's bytes>"},
    "mobile_panel":  {"source": "final-mockups/<stitched mobile mockup>",
                      "sha256": "<sha256 of that file's bytes>"},
    "guide": {
      "typography_source": "font-action-plan/font-map.json",
      "sections": [
        {"number": 1, "section_id": "<id>", "name": "<section name>",
         "wireframe_thumbnail": "desktop-wireframe/section-01.png",
         "sha256": "<sha256 of the thumbnail's bytes>",
         "type_specs": {"heading": "...", "body": "...", "cta": "..."}}
      ]
    }
  }

This validator is the deterministic floor. It checks:

  1. Both panels name a file inside final-mockups/ whose bytes hash to
     the recorded sha256, so a panel can only ever be the approved
     mockup artifact the record names; a panel whose source changed
     after the record was written fails by name.
  2. The guide's sections are numbered consecutively from 1, each with
     its name, a mini wireframe thumbnail under desktop-wireframe/
     whose bytes hash to the recorded sha256, and typography specs
     (heading, body, CTA) drawn from the named typography spec record,
     which must exist in the run.
  3. The guide matches the mockups (H2): when the stage's production
     record (final-mockups/production-record.json) or the desktop
     wireframe section plan (desktop-wireframe/section-plan.json) is
     present in the run, the guide's section ids equal that record's
     section ids, in order.
  4. Per-section typography (1.3.59): when the typography source (the
     font map) carries its `typography` list, each guide section's
     type_specs equal what the font map gives THAT section, and only the
     elements the section has: the hero section (the one the font map's
     hero_headline serves) prints the hero headline spec, every other
     section the section_heading spec; a CTA spec is present only for a
     section the font map's `ctas` names and absent for every other. A
     section with no button must not print a CTA spec.
  5. With --check-board: the composed board exists, and its receipt
     (final-mockups/hybrid-board-receipt.json) names the same input
     hashes as the record and the board file's own sha256, so a board
     composed from other artifacts, or an input changed after
     composition, fails by name. The receipt's guide block must also
     show (1.3.59) that each guide section's block sits at its mockup
     section's own vertical position (the desktop stitch receipt's
     y_offset scaled to the panel, within ALIGN_TOLERANCE_PX), that the
     thumbnails are drawn at no less than MIN_THUMB_SCALE of the
     wireframe slice's own size (so the wireframe's printed annotations
     stay readable), and, when Pillow is present, that the thumbnail
     pixels are on the board at the recorded place.

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
# The guide column is a presentation of the wireframe slices, whose printed annotations are about 25 px
# tall at the 1440 px page width: a thumbnail drawn below half size shrinks them under 12 px, unreadable.
MIN_THUMB_SCALE = 0.5
ALIGN_TOLERANCE_PX = 4


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _size_phrase(element):
    sizes = (element or {}).get("sizes") or {}
    parts = []
    for viewport in ("desktop", "tablet"):
        size = sizes.get(viewport)
        if isinstance(size, dict) and "px" in size and "line_height" in size:
            parts.append(f"{size['px']}px / {size['line_height']} {viewport}")
    return ", ".join(parts)


def _family(font_map, role):
    fam = ((font_map.get("families") or {}).get(role) or {}).get("family")
    return fam or (font_map.get("fonts") or {}).get(role)


def _spec(font_map, element, extras=False):
    phrase = _size_phrase(element)
    family = _family(font_map, (element or {}).get("role"))
    if not phrase or not family:
        return None
    text = f"{family} {phrase}"
    if extras:
        if element.get("style"):
            text += f", {element['style']}"
        if element.get("letter_spacing"):
            text += f", tracking {element['letter_spacing']}"
    return text


def hero_section_id(font_map, first_id):
    """The section the font map's hero headline serves ('Section 1 headline: ...'); else the first."""
    for el in font_map.get("typography") or []:
        if isinstance(el, dict) and el.get("element") == "hero_headline":
            m = re.match(r"\s*Section\s+([A-Za-z0-9_-]+)", str(el.get("serves") or ""))
            if m:
                return m.group(1)
    return first_id


def derive_type_specs(font_map, section_ids):
    """What the closed font map gives each section: {section_id: {"heading", "body"[, "cta"]}}, only the
    elements the section has. Returns None when the font map carries no usable typography list (a record
    whose source is not a real font map is validated structurally only, as before)."""
    if not isinstance(font_map, dict) or not isinstance(font_map.get("typography"), list):
        return None
    by_name = {e.get("element"): e for e in font_map["typography"] if isinstance(e, dict)}
    body = _spec(font_map, by_name.get("body"))
    hero = _spec(font_map, by_name.get("hero_headline"))
    heading = _spec(font_map, by_name.get("section_heading"))
    cta = _spec(font_map, by_name.get("cta_label"), extras=True)
    if not (body and hero and heading):
        return None
    ctas = font_map.get("ctas")
    cta_sections = {str(c.get("section")) for c in ctas if isinstance(c, dict)} if isinstance(ctas, list) else None
    hero_id = hero_section_id(font_map, section_ids[0] if section_ids else None)
    out = {}
    for sid in section_ids:
        specs = {"heading": hero if sid == hero_id else heading, "body": body}
        if cta_sections is None or sid in cta_sections:
            if cta:
                specs["cta"] = cta
        out[sid] = specs
    return out


def _type_spec_failures(guide, run_dir):
    """Per-section typography against the font map (see the module docstring, 4)."""
    if run_dir is None or not isinstance(guide, dict):
        return []
    typo = guide.get("typography_source")
    if not isinstance(typo, str) or not typo:
        return []
    font_map = _read_json(Path(run_dir) / typo)
    sections = [s for s in guide.get("sections") or [] if isinstance(s, dict) and isinstance(s.get("section_id"), str)]
    derived = derive_type_specs(font_map, [s["section_id"] for s in sections])
    if derived is None:
        return []
    out = []
    for s in sections:
        sid, want, got = s["section_id"], derived[s["section_id"]], s.get("type_specs")
        if not isinstance(got, dict):
            continue
        for field in ("heading", "body", "cta"):
            if field in want:
                if got.get(field) != want[field]:
                    out.append(f"guide section {sid}: type_specs.{field} is {got.get(field)!r}, the font map "
                               f"({typo}) gives this section {want[field]!r}")
            elif field in got:
                out.append(f"guide section {sid}: type_specs.{field} is printed ({got[field]!r}) but the font map "
                           f"({typo}) gives this section no {field.upper() if field == 'cta' else field} "
                           f"(print only the elements the section has)")
    return out


def _panel_failures(data, key, run_dir):
    failures = []
    panel = data.get(key)
    if not isinstance(panel, dict):
        return [f"{key} is required (an object naming the approved panel artifact and its sha256)"]
    source = panel.get("source")
    if not isinstance(source, str) or not source:
        failures.append(f"{key}.source is required (the approved mockup artifact, run-relative)")
    elif not source.startswith("final-mockups/"):
        failures.append(f"{key}.source must be inside final-mockups/ (the mockup stage's own approved artifacts): {source}")
    recorded = panel.get("sha256")
    if not isinstance(recorded, str) or not SHA_RE.match(recorded):
        failures.append(f"{key}.sha256 must be the 64-hex sha256 of the panel file's bytes")
        recorded = None
    if isinstance(source, str) and source and recorded is not None and run_dir is not None:
        path = Path(run_dir) / source
        if not path.exists():
            failures.append(f"{key}: panel file is not on disk: {source}")
        elif sha256(path) != recorded:
            failures.append(
                f"{key}: panel file {source} does not hash to the recorded sha256 "
                "(the panel must be the approved artifact the record names, byte for byte)")
    return failures


def _section_ids_from(path, kind):
    """Section ids of a production record or section plan, or None."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    if kind == "production-record" and isinstance(data, dict):
        sections = data.get("sections")
        if isinstance(sections, list):
            return [s.get("section_id") for s in sections if isinstance(s, dict)]
    if kind == "section-plan" and isinstance(data, list):
        return [s.get("section_id") for s in data if isinstance(s, dict)]
    return None


def _refreshed_from_failures(data):
    """A record re-pinned by build_hybrid_board.py --refresh-record carries its provenance; when the
    block is present its own content hash must hold and its new panels must be the record's panels.
    Additive: a record without the block is untouched."""
    block = data.get("refreshed_from")
    if block is None:
        return []
    if not isinstance(block, dict):
        return ["refreshed_from must be an object"]
    body = {k: v for k, v in block.items() if k != "receipt_sha256"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if block.get("receipt_sha256") != digest:
        return ["refreshed_from.receipt_sha256 does not match the block's content (the provenance was edited)"]
    out = []
    new = block.get("new") or {}
    for key in ("desktop_panel", "mobile_panel"):
        if new.get(key) != data.get(key):
            out.append(f"{key} differs from refreshed_from.new.{key}: the record was changed after its refresh")
    guide_block = block.get("guide")
    if guide_block is not None:  # SWB-290: the guide thumbnails were re-pinned too
        recorded = {str(x.get("section_id")): (x.get("wireframe_thumbnail"), x.get("sha256"))
                    for x in ((data.get("guide") or {}).get("sections") or []) if isinstance(x, dict)}
        for row in (guide_block.get("new") if isinstance(guide_block, dict) else None) or []:
            if recorded.get(str(row.get("section_id"))) != (row.get("wireframe_thumbnail"), row.get("sha256")):
                out.append(f"guide section {row.get('section_id')} differs from refreshed_from.guide.new: "
                           f"the record was changed after its refresh")
    spec_block = block.get("guide_type_specs")
    if spec_block is not None:  # SWB-580: the per-section type specs were re-derived from the font map
        recorded = {str(x.get("section_id")): x.get("type_specs")
                    for x in ((data.get("guide") or {}).get("sections") or []) if isinstance(x, dict)}
        new_specs = spec_block.get("new") if isinstance(spec_block, dict) else None
        for sid, specs in (new_specs or {}).items():
            if recorded.get(str(sid)) != specs:
                out.append(f"guide section {sid}: type_specs differ from refreshed_from.guide_type_specs.new: "
                           f"the record was changed after its refresh")
    return out


def check_board(data, run_dir=None):
    """Return a list of named failure strings; empty means the record passes.

    run_dir, when given, is the run folder the record's run-relative
    sources resolve against; file existence and hash checks run only then.
    """
    failures = []
    if not isinstance(data, dict):
        return ["hybrid board record is not a JSON object"]
    output = data.get("board_output", "hybrid-board.png")
    if not isinstance(output, str) or not output.lower().endswith(".png") or "/" in output:
        failures.append("board_output must be a PNG filename inside final-mockups/ (default hybrid-board.png)")

    failures.extend(_panel_failures(data, "desktop_panel", run_dir))
    failures.extend(_panel_failures(data, "mobile_panel", run_dir))

    failures.extend(_refreshed_from_failures(data))

    guide = data.get("guide")
    if not isinstance(guide, dict):
        failures.append("guide is required (the section guide column: typography source and ordered sections)")
        return failures
    typo_source = guide.get("typography_source")
    if not isinstance(typo_source, str) or not typo_source:
        failures.append("guide.typography_source is required (the typography spec record the guide's specs are drawn from)")
    elif run_dir is not None and not (Path(run_dir) / typo_source).exists():
        failures.append(f"guide.typography_source is not on disk: {typo_source}")

    sections = guide.get("sections")
    if not isinstance(sections, list) or not sections:
        failures.append("guide.sections must be a non-empty ordered array")
        return failures
    seen = set()
    guide_ids = []
    for i, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            failures.append(f"guide.sections[{i}] is not an object")
            continue
        sid = section.get("section_id")
        label = sid if isinstance(sid, str) and sid else f"guide.sections[{i}]"
        if section.get("number") != i:
            failures.append(f"guide section {label}: number must be {i} (the guide's sections are numbered consecutively from 1)")
        if not isinstance(sid, str) or not sid:
            failures.append(f"guide.sections[{i}]: section_id is required")
        elif sid in seen:
            failures.append(f"guide section {sid}: duplicated section_id")
        else:
            seen.add(sid)
            guide_ids.append(sid)
        if not isinstance(section.get("name"), str) or not section.get("name"):
            failures.append(f"guide section {label}: name is required (the section's name, printed in the guide column)")
        thumb = section.get("wireframe_thumbnail")
        if not isinstance(thumb, str) or not thumb:
            failures.append(f"guide section {label}: wireframe_thumbnail is required (the section's mini wireframe thumbnail)")
        elif not thumb.startswith("desktop-wireframe/"):
            failures.append(f"guide section {label}: wireframe_thumbnail must be the section's desktop wireframe slice under desktop-wireframe/: {thumb}")
        recorded = section.get("sha256")
        if not isinstance(recorded, str) or not SHA_RE.match(recorded or ""):
            failures.append(f"guide section {label}: sha256 must be the 64-hex sha256 of the thumbnail file's bytes")
            recorded = None
        if isinstance(thumb, str) and thumb and recorded is not None and run_dir is not None:
            path = Path(run_dir) / thumb
            if not path.exists():
                failures.append(f"guide section {label}: wireframe thumbnail is not on disk: {thumb}")
            elif sha256(path) != recorded:
                failures.append(
                    f"guide section {label}: thumbnail {thumb} does not hash to the recorded sha256 "
                    "(the guide's thumbnails must be the approved wireframe slices, byte for byte)")
        specs = section.get("type_specs")
        cta_optional = False
        if run_dir is not None and isinstance(sid, str) and sid and isinstance(typo_source, str) and typo_source:
            derived_one = derive_type_specs(_read_json(Path(run_dir) / typo_source), [sid])
            cta_optional = derived_one is not None and "cta" not in derived_one[sid]
        if not isinstance(specs, dict):
            failures.append(f"guide section {label}: type_specs is required (the section's typography specs: heading, body, cta)")
        else:
            for field in ("heading", "body", "cta"):
                if field == "cta" and cta_optional:
                    continue  # the font map gives this section no button: the spec is validated absent below
                if not isinstance(specs.get(field), str) or not specs.get(field):
                    failures.append(f"guide section {label}: type_specs.{field} is required (the section's printed typography spec)")

    failures.extend(_type_spec_failures(guide, run_dir))

    if run_dir is not None and guide_ids:
        run_dir = Path(run_dir)
        for rel, kind, what in (
            ("final-mockups/production-record.json", "production-record",
             "the mockup production record"),
            ("desktop-wireframe/section-plan.json", "section-plan",
             "the desktop wireframe section plan"),
        ):
            path = run_dir / rel
            if not path.exists():
                continue
            ids = _section_ids_from(path, kind)
            if ids is not None and ids != guide_ids:
                failures.append(
                    f"guide sections {guide_ids} do not match {what} ({rel}): {ids} "
                    "(trait H2: the guide matches the mockups, section for section, in order)")
    return failures


def check_composed_board(data, run_dir):
    """With --check-board: the composed board and its receipt must match the record."""
    failures = []
    run_dir = Path(run_dir)
    output = data.get("board_output", "hybrid-board.png") if isinstance(data, dict) else "hybrid-board.png"
    board = run_dir / "final-mockups" / output
    if not board.exists():
        return [f"hybrid board is not on disk: final-mockups/{output} "
                "(compose it with scripts/build_hybrid_board.py)"]
    receipt_path = run_dir / "final-mockups" / "hybrid-board-receipt.json"
    if not receipt_path.exists():
        return failures + ["hybrid board receipt is not on disk: final-mockups/hybrid-board-receipt.json "
                           "(the composer's receipt is the board's composition proof)"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return failures + [f"could not read hybrid board receipt: {exc}"]
    if receipt.get("board_output") != output:
        failures.append(f"receipt board_output {receipt.get('board_output')!r} does not name this board ({output!r})")
    if receipt.get("output_sha256") != sha256(board):
        failures.append("the board file does not hash to the receipt's output_sha256 "
                        "(the board on disk is not the board the receipt composed)")
    expected_inputs = {}
    for key in ("desktop_panel", "mobile_panel"):
        panel = data.get(key) or {}
        if isinstance(panel.get("source"), str):
            expected_inputs[panel["source"]] = panel.get("sha256")
    for section in (data.get("guide") or {}).get("sections") or []:
        if isinstance(section, dict) and isinstance(section.get("wireframe_thumbnail"), str):
            expected_inputs[section["wireframe_thumbnail"]] = section.get("sha256")
    receipt_inputs = {item.get("source"): item.get("sha256")
                      for item in receipt.get("inputs") or [] if isinstance(item, dict)}
    if receipt_inputs != expected_inputs:
        failures.append("the receipt's input hashes do not match the board record "
                        "(the board must be composed from exactly the artifacts the record names)")
    failures.extend(_guide_geometry_failures(data, receipt, run_dir, board))
    return failures


def _desktop_tops(data, receipt, run_dir):
    """{section_id: expected top y on the sheet} recomputed from the desktop stitch receipt (never from the
    composer's own receipt), or None when the run carries no stitch receipt for the desktop panel."""
    source = ((data.get("desktop_panel") or {}).get("source"))
    if not isinstance(source, str):
        return None
    stitch = _read_json(Path(run_dir) / Path(source).parent / "stitch-receipt.json")
    panel = (receipt.get("panels") or {}).get("desktop") or {}
    if not isinstance(stitch, dict) or not stitch.get("page_width") or not panel.get("width"):
        return None
    scale = panel["width"] / stitch["page_width"]
    return {str(r.get("section_id")): panel["y"] + round(r["y_offset"] * scale)
            for r in stitch.get("sections") or [] if isinstance(r, dict) and "y_offset" in r}


def _guide_geometry_failures(data, receipt, run_dir, board):
    """1.3.59: the guide blocks sit at their mockup sections, and the wireframe thumbnails are readable."""
    guide = receipt.get("guide")
    if not isinstance(guide, dict) or not isinstance(guide.get("sections"), list):
        return ["the board receipt carries no guide geometry (compose the board again with "
                "scripts/build_hybrid_board.py; a board composed before 1.3.59 stacked the guide from the top "
                "and printed the wireframe annotations at about 7 px)"]
    out = []
    expected = _desktop_tops(data, receipt, run_dir)
    rows = {str(r.get("section_id")): r for r in guide["sections"] if isinstance(r, dict)}
    ids = [str(x.get("section_id")) for x in (data.get("guide") or {}).get("sections") or [] if isinstance(x, dict)]
    if list(rows) != ids:
        out.append(f"the board receipt's guide sections {list(rows)} are not the record's {ids}, in order")
    for sid in ids:
        row = rows.get(sid)
        if row is None:
            continue
        thumb = row.get("thumbnail") or {}
        scale = row.get("thumbnail_scale")
        if not isinstance(scale, (int, float)) or scale < MIN_THUMB_SCALE:
            out.append(f"guide section {sid}: the wireframe thumbnail is drawn at {scale!r} of its own size, below "
                       f"{MIN_THUMB_SCALE}; its printed annotations are unreadable at that size")
        top = (expected or {}).get(sid)
        if top is None:
            top = row.get("mockup_top")
            if expected is not None:
                out.append(f"guide section {sid}: the desktop stitch receipt has no section {sid}")
                continue
        if not isinstance(top, (int, float)) or not isinstance(thumb.get("y"), int):
            out.append(f"guide section {sid}: the board receipt records no thumbnail position")
            continue
        drift = abs(thumb["y"] - top)
        if drift > ALIGN_TOLERANCE_PX:
            out.append(f"guide section {sid}: its block sits {drift} px from the mockup section it describes "
                       f"(block at y {thumb['y']}, mockup section at y {top}; tolerance {ALIGN_TOLERANCE_PX} px)")
    if out or run_dir is None:
        return out
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError:
        return out
    try:
        with Image.open(board) as im:
            sheet = im.convert("RGB")
        for section in (data.get("guide") or {}).get("sections") or []:
            row = rows.get(str(section.get("section_id"))) or {}
            thumb = row.get("thumbnail") or {}
            with Image.open(Path(run_dir) / section["wireframe_thumbnail"]) as t:
                want = t.convert("RGB").resize((thumb["width"], thumb["height"]))
            box = (thumb["x"], thumb["y"], thumb["x"] + thumb["width"], thumb["y"] + thumb["height"])
            got = sheet.crop(box)
            if got.size != want.size or sum(ImageStat.Stat(ImageChops.difference(got, want)).mean) / 3 > 2.0:
                out.append(f"guide section {section.get('section_id')}: the board does not show the pinned wireframe "
                           f"thumbnail at the place its receipt records")
    except Exception as exc:  # unreadable pixels are a failure, not a pass
        out.append(f"the board's guide thumbnails could not be checked against the board pixels ({type(exc).__name__})")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a run's hybrid board record (and, with --check-board, the composed board).")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--record", default="hybrid-board.json",
                        help="Board record filename inside final-mockups/ (default hybrid-board.json).")
    parser.add_argument("--check-board", action="store_true",
                        help="Also require the composed board and its receipt to match the record.")
    args = parser.parse_args(argv)

    record_path = args.run_dir / "final-mockups" / args.record
    try:
        data = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read hybrid board record: {exc}")
        return 2
    failures = check_board(data, run_dir=args.run_dir)
    if args.check_board and not failures:
        failures = check_composed_board(data, args.run_dir)
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    count = len(data["guide"]["sections"])
    extra = " and the composed board matches its receipt" if args.check_board else ""
    print(f"PASS: hybrid board record names the approved desktop and mobile panels and a "
          f"{count}-section guide matching the mockups{extra}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
