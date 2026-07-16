#!/usr/bin/env python3
"""U91 (X/U-X1) — Master-spec banned-term scrub verification.

U92 (X/U-X2, `scripts/check-docs-language.py`) is a forward-looking, DIFF-scoped
guard: it only ever inspects lines newly ADDED by a change, so it can never, by
itself, confirm the ONE-TIME claim MASTER SPEC v2 X.1.2 makes about the fully
assembled document as a whole — that a case-insensitive search of the entire
spec text finds the retired term only inside (a) the LANGUAGE CONFORMANCE
header's single defining sentence, where the term must be spelled out once to
be defined at all, and (b)/(c) the annotated legacy-filename / vendor-literal
citations already tracked in `scripts/docs-language-allowlist.json`.

This script is that whole-document check — the "verification run" X.1.2 calls
for, made a real, re-runnable repo artifact instead of a one-off manual claim.
It is deliberately independent of git diffs: it reads one file, start to
finish, and classifies every line that contains the term into exactly one of:

  * `defining_sentence`               — the single raw occurrence inside the
                                         LANGUAGE CONFORMANCE header's marker
                                         window (see --defining-sentence-*).
                                         Only the FIRST qualifying occurrence
                                         is ever accepted this way — a second
                                         one is proof the term is not, in
                                         fact, "defined once", and is treated
                                         as a genuine violation.
  * `legacy_filename_or_vendor_literal` — every occurrence on the line is
                                         explained by an allowlisted literal
                                         (same subtraction rule U92 uses: a
                                         literal on the same line as a stray,
                                         unexplained occurrence does NOT
                                         amnesty that stray occurrence).
  * `UNEXPLAINED`                     — anything else. One or more of these
                                         means the binary scrub target is
                                         NOT met.

Reuses the same allowlist file as U92 (single source of truth for the term,
legacy filenames, and vendor literals) rather than duplicating those literals
here. Two widenings on top of U92's exact-substring rule, both because the
assembled spec is cross-repo planning prose, not repo diff content:

  * A tracked legacy filename may be cited by its BASENAME alone (e.g. the
    tail of one of the six paths in scripts/docs-language-allowlist.json,
    without its leading directory) when a paragraph has already established
    the directory context — still an unambiguous, specific citation of the
    same tracked file, never a generic phrase.
  * `--extra-citations` (default scripts/verify-master-spec-scrub-extra-citations.json,
    a file this unit owns) adds legacy filenames the spec legitimately cites
    that live OUTSIDE this repo (see that file for the one current entry, a
    blackceo-command-center legacy reset script tracked under Decision D13)
    — out of scope for U92's ONB-only CI allowlist by design, but still a
    real, annotated Class B citation per MASTER SPEC v2 X.1.3.

Usage:
    python3 scripts/verify-master-spec-scrub.py --spec-path <path-to-assembled-spec.md>
    python3 scripts/verify-master-spec-scrub.py --spec-path <path> --no-require-defining-sentence

Exit codes: 0 = binary scrub target MET. 1 = violation (or, unless
--no-require-defining-sentence, no defining-sentence occurrence found at
all). 2 = usage/environment error (missing file, unreadable allowlist).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

DEFAULT_ALLOWLIST = Path(__file__).resolve().parent / "docs-language-allowlist.json"
DEFAULT_EXTRA_CITATIONS = (
    Path(__file__).resolve().parent / "verify-master-spec-scrub-extra-citations.json"
)
DEFAULT_DEFINING_MARKER = "LANGUAGE CONFORMANCE"
# How many lines after a defining-marker heading the one raw "spells it out"
# occurrence is allowed to appear in. Generous on purpose: this is a coarse
# "is this occurrence plausibly part of the header that defines the term"
# heuristic, not a section parser — a real stray violation elsewhere in a
# multi-thousand-line document will never happen to fall inside this window.
DEFAULT_DEFINING_WINDOW = 40


class Occurrence(NamedTuple):
    line_no: int
    text: str
    classification: str  # "defining_sentence" | "legacy_filename_or_vendor_literal" | "UNEXPLAINED"


def load_allowlist(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_extra_citations(path: Path | None) -> dict:
    """Optional, U91-owned supplement (see module docstring). Missing file
    is not an error — it just means no supplemental citations are known."""
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _literals_from_allowlist(allowlist: dict, extra_citations: dict) -> list[str]:
    legacy_paths = [
        e["path"] for e in allowlist.get("legacy_filenames", {}).get("entries", [])
    ]
    legacy_paths += [
        e["path"] for e in extra_citations.get("legacy_filenames", {}).get("entries", [])
    ]
    # Full canonical paths, PLUS each one's basename alone — a paragraph that
    # has already established directory context may cite the bare filename
    # (see module docstring). Basenames of these specific tracked files are
    # distinctive, never generic English words, so this never over-amnesties
    # unrelated prose.
    literals = list(legacy_paths)
    literals += [Path(p).name for p in legacy_paths]
    literals += list(allowlist.get("vendor_literals", {}).get("entries", []))
    return literals


def _covered_spans(line: str, literals: list[str]) -> list[tuple[int, int]]:
    """Character spans on `line` explained by an allowlisted legacy filename
    or vendor literal (case-insensitive substring match) — same subtraction
    rule as U92's `Allowlist.uncovered_matches`."""
    spans: list[tuple[int, int]] = []
    line_lower = line.lower()
    for literal in literals:
        if not literal:
            continue
        lit_lower = literal.lower()
        start = 0
        while True:
            idx = line_lower.find(lit_lower, start)
            if idx == -1:
                break
            spans.append((idx, idx + len(literal)))
            start = idx + 1
    return spans


def scan_spec(
    spec_path: Path,
    allowlist: dict,
    defining_marker: str,
    defining_window: int,
    extra_citations: dict | None = None,
) -> tuple[list[Occurrence], bool]:
    """Returns (occurrences, defining_sentence_found)."""
    term_re = re.compile(re.escape(allowlist["term"]), re.IGNORECASE)
    literals = _literals_from_allowlist(allowlist, extra_citations or {})
    marker_re = re.compile(re.escape(defining_marker), re.IGNORECASE)

    occurrences: list[Occurrence] = []
    defining_sentence_found = False
    lines_since_marker: int | None = None

    with spec_path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.rstrip("\n")

            if marker_re.search(line):
                lines_since_marker = 0
            elif lines_since_marker is not None:
                lines_since_marker += 1
                if lines_since_marker > defining_window:
                    lines_since_marker = None

            if not term_re.search(line):
                continue

            spans = _covered_spans(line, literals)
            uncovered = [
                m
                for m in term_re.finditer(line)
                if not any(s <= m.start() and m.end() <= e for s, e in spans)
            ]

            if not uncovered:
                occurrences.append(
                    Occurrence(line_no, line, "legacy_filename_or_vendor_literal")
                )
                continue

            in_window = lines_since_marker is not None
            if in_window and not defining_sentence_found:
                defining_sentence_found = True
                occurrences.append(Occurrence(line_no, line, "defining_sentence"))
                continue

            occurrences.append(Occurrence(line_no, line, "UNEXPLAINED"))

    return occurrences, defining_sentence_found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec-path", required=True, type=Path,
                         help="Path to the fully assembled spec document to scan.")
    parser.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST), type=Path,
                         help="Path to the shared docs-language-allowlist.json (U92's file).")
    parser.add_argument("--extra-citations", default=str(DEFAULT_EXTRA_CITATIONS), type=Path,
                         help="Path to U91's supplemental cross-repo legacy-filename "
                              "citations file. Missing file is not an error.")
    parser.add_argument("--defining-sentence-marker", default=DEFAULT_DEFINING_MARKER,
                         help="Heading text that opens the term's defining-sentence window.")
    parser.add_argument("--defining-sentence-window", default=DEFAULT_DEFINING_WINDOW, type=int,
                         help="Max lines after the marker in which the one raw defining "
                              "occurrence is accepted.")
    parser.add_argument("--no-require-defining-sentence", action="store_true",
                         help="Do not fail if zero defining-sentence occurrences are found "
                              "(useful for scanning excerpts that don't include the header).")
    args = parser.parse_args(argv)

    if not args.spec_path.is_file():
        print(f"verify-master-spec-scrub: ERROR: spec file not found: {args.spec_path}",
              file=sys.stderr)
        return 2

    try:
        allowlist = load_allowlist(Path(args.allowlist))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"verify-master-spec-scrub: ERROR: could not load allowlist "
              f"{args.allowlist}: {exc}", file=sys.stderr)
        return 2

    try:
        extra_citations = load_extra_citations(Path(args.extra_citations))
    except json.JSONDecodeError as exc:
        print(f"verify-master-spec-scrub: ERROR: could not load extra-citations "
              f"{args.extra_citations}: {exc}", file=sys.stderr)
        return 2

    occurrences, defining_found = scan_spec(
        args.spec_path, allowlist, args.defining_sentence_marker,
        args.defining_sentence_window, extra_citations,
    )
    unexplained = [o for o in occurrences if o.classification == "UNEXPLAINED"]
    legacy = [o for o in occurrences if o.classification == "legacy_filename_or_vendor_literal"]
    defining = [o for o in occurrences if o.classification == "defining_sentence"]

    print(f"verify-master-spec-scrub: {args.spec_path}: "
          f"{len(occurrences)} line(s) contain the retired term.")
    print(f"  defining sentence: {len(defining)} line(s) {[o.line_no for o in defining]}")
    print(f"  legacy filename / vendor literal citations: {len(legacy)} line(s) "
          f"{[o.line_no for o in legacy]}")
    print(f"  UNEXPLAINED (violations): {len(unexplained)} line(s)")
    for o in unexplained:
        print(f"    L{o.line_no}: {o.text.strip()}")

    ok = not unexplained
    if not args.no_require_defining_sentence and not defining_found:
        print(
            "verify-master-spec-scrub: WARNING: no defining-sentence occurrence found "
            f"within {args.defining_sentence_window} lines of a "
            f"{args.defining_sentence_marker!r} marker."
        )
        ok = False

    print(f"verify-master-spec-scrub: {'PASS' if ok else 'FAIL'} — binary scrub target "
          f"{'MET' if ok else 'NOT MET'}.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
