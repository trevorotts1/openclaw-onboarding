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
  4. With --check-board: the composed board exists, and its receipt
     (final-mockups/hybrid-board-receipt.json) names the same input
     hashes as the record and the board file's own sha256, so a board
     composed from other artifacts, or an input changed after
     composition, fails by name.

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
        if not isinstance(specs, dict):
            failures.append(f"guide section {label}: type_specs is required (the section's typography specs: heading, body, cta)")
        else:
            for field in ("heading", "body", "cta"):
                if not isinstance(specs.get(field), str) or not specs.get(field):
                    failures.append(f"guide section {label}: type_specs.{field} is required (the section's printed typography spec)")

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
    return failures


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
