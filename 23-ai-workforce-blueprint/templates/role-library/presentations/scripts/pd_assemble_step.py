#!/usr/bin/env python3
"""pd_assemble_step.py -- the P8-ASSEMBLE executor (PD-062, decision D-12).

WHY THIS EXISTS
---------------
`P8-ASSEMBLE` used to be an AGENT step: the manifest declared
`produces_artifact: "*-FINAL.pptx"` but no executor wrote or verified the deck
where its consumers (P8.1-PDF-EXPORT, P8.2-GUIDE, P8.15-MOTION, P8.25-WORKBOOK,
P9.5-NOTES-SYNC) look for it, and the dispatcher declined the phase by name.
The render (P4-RENDER -> build_deck.py) already writes the assembled deck to
`<run>/working/deliverables/out-FINAL.pptx`; this script is the mechanical step
that confirms that deck is the real thing and, when it is not, re-runs assembly
from the banked renders.

WHAT IT DOES
------------
  1. Finds exactly one `<run>/working/deliverables/*-FINAL.pptx`.
  2. Verifies it is a ZIP that holds `ppt/presentation.xml` and has one slide
     per row of `<run>/working/copy/slides.json`.
  3. Exit 0 when valid.
  4. When the deck is absent or invalid, re-runs assembly from
     `<run>/renders/slide-*.png` by calling `build_deck.assemble_pptx` -- the
     exact function the render calls (RD-03) -- and re-verifies the result.
     Exit non-zero with the reason when that cannot produce a valid deck.

It NEVER calls an image service and NEVER fetches anything: the renders are
already on disk. Stdlib only, except for the canonical assembler it imports.

EXIT CODES
  0  a valid deck is present (already valid, or reassembled from banked renders)
  2  usage error (bad --run-dir)
  3  no valid deck and it could not be reassembled (the reason names what is missing)

USAGE
  python3 scripts/pd_assemble_step.py --run-dir <run_dir> [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

_FINAL_GLOB = "*-FINAL.pptx"
_SLIDE_MEMBER_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")
_RENDER_RE = re.compile(r"slide-(\d+)\.png$")


def _slides_row_count(run_dir: Path) -> tuple[int | None, str]:
    """Rows in working/copy/slides.json, or (None, why) when it cannot be read."""
    path = run_dir / "working" / "copy" / "slides.json"
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None, f"slides.json not found at {path}"
    except (OSError, ValueError) as exc:
        return None, f"slides.json unreadable at {path}: {exc}"
    if not isinstance(data, list):
        return None, f"slides.json at {path} is not a list of slide rows"
    return len(data), ""


def _deck_problem(deck: Path, expected_slides: int | None) -> str:
    """Empty string when the deck is valid, else the reason."""
    try:
        if not zipfile.is_zipfile(deck):
            return f"{deck} is not a ZIP container"
        with zipfile.ZipFile(deck) as zf:
            names = zf.namelist()
    except OSError as exc:
        return f"{deck} could not be opened: {exc}"
    if "ppt/presentation.xml" not in names:
        return f"{deck} holds no ppt/presentation.xml"
    slide_count = sum(1 for n in names if _SLIDE_MEMBER_RE.match(n))
    if expected_slides is not None and slide_count != expected_slides:
        return (f"{deck} has {slide_count} slide(s) but working/copy/slides.json "
                f"has {expected_slides} row(s)")
    if slide_count == 0:
        return f"{deck} has no slides"
    return ""


def _banked_renders(run_dir: Path) -> tuple[list[dict], str]:
    """Renders on disk as assemble_pptx input rows, or ([], why)."""
    renders_dir = run_dir / "renders"
    rows: list[dict] = []
    for png in renders_dir.glob("slide-*.png"):
        m = _RENDER_RE.search(png.name)
        if not m:
            continue
        rows.append({"slide": int(m.group(1)), "file": str(png)})
    rows.sort(key=lambda r: r["slide"])
    if not rows:
        return [], f"no banked renders at {renders_dir}/slide-*.png"
    return rows, ""


def _reassemble(run_dir: Path, out_path: Path, rows: list[dict]) -> str:
    """Run the canonical assembler; return a reason string ('' on success)."""
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import build_deck
    except Exception as exc:  # noqa: BLE001 -- report, never traceback at a gate
        return f"cannot import the canonical assembler build_deck: {exc}"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        build_deck.assemble_pptx(rows, out_path)
    except SystemExit as exc:
        return f"canonical assembler exited {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return f"canonical assembler failed: {exc}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="P8-ASSEMBLE executor: confirm or rebuild the FINAL deck.")
    ap.add_argument("--run-dir", required=True,
                    help="the governed run folder (contains working/ and renders/)")
    ap.add_argument("--json", action="store_true", help="print a JSON summary")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir is not a directory: {run_dir}", file=sys.stderr)
        return 2

    deliverables = run_dir / "working" / "deliverables"
    expected, slides_note = _slides_row_count(run_dir)
    if slides_note:
        print(f"WARNING: slide count cannot be checked: {slides_note}",
              file=sys.stderr, flush=True)

    decks = sorted(p for p in deliverables.glob(_FINAL_GLOB) if p.is_file())
    if len(decks) > 1:
        print(f"FATAL: more than one {_FINAL_GLOB} under {deliverables}: "
              f"{', '.join(p.name for p in decks)} -- the run is ambiguous; remove "
              f"the stale deck, then re-run this step.", file=sys.stderr)
        return 3

    problem = ""
    if decks:
        problem = _deck_problem(decks[0], expected)
        if not problem:
            _emit(args.json, {"ok": True, "action": "verified",
                              "deck": str(decks[0]), "slides": expected})
            return 0
        print(f"INVALID DECK: {problem}", file=sys.stderr, flush=True)
    else:
        problem = f"no {_FINAL_GLOB} under {deliverables}"

    rows, renders_problem = _banked_renders(run_dir)
    if renders_problem:
        print(f"FATAL: {problem}; {renders_problem}. P8-ASSEMBLE cannot produce a "
              f"deck: the render wrote neither a deck nor its slide renders.",
              file=sys.stderr)
        return 3

    out_path = (decks[0] if decks else deliverables / "out-FINAL.pptx")
    reason = _reassemble(run_dir, out_path, rows)
    if reason:
        print(f"FATAL: {problem}; reassembly from {len(rows)} banked render(s) "
              f"failed: {reason}", file=sys.stderr)
        return 3
    problem = _deck_problem(out_path, expected)
    if problem:
        print(f"FATAL: reassembled from {len(rows)} banked render(s) but the "
              f"result is still invalid: {problem}", file=sys.stderr)
        return 3

    _emit(args.json, {"ok": True, "action": "reassembled",
                      "deck": str(out_path), "slides": expected,
                      "renders": len(rows)})
    return 0


def _emit(as_json: bool, payload: dict) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"OK P8-ASSEMBLE ({payload['action']}): {payload['deck']}")


if __name__ == "__main__":
    sys.exit(main())
