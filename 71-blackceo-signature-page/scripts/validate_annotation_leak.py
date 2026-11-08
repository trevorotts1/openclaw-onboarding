#!/usr/bin/env python3
"""Fail a built page that still carries its production annotations.

The mockup and the built page are the client's finished page: the numbered
section chip ("SECTION 4 of 15"), the name tab ("SECOND PROBLEM"), the type-spec
labels, the layout-block headings and the wireframe behaviour notes ("CTA below
the copy") are production scaffolding and must never be drawn into either.

scripts/validate_public_copy.py already screens some production labels, but its
section-label pattern needs a colon after the number and is line-anchored, so a
chip that reads exactly `SECTION 4` in the middle of a line passes it. This
validator is the structural guard that closes that gap: the same markup
(`<div class="chip">SECTION 4</div>`, a SECOND PROBLEM tab, a
`<p>CTA below the copy</p>`) exits 1 here.

The denylist is DERIVED BY IMPORT, never restated, so it cannot drift from the
prompt builder it polices:

  (a) every value of build_production_request.ROLE_NAMES;
  (b) the section_name of every section in <run_dir>/production-request.json;
  (c) wireframe_spec._note() output for each of those sections under
      'desktop-wireframe' and 'mobile-tablet', plus the four fallbacks;
  (d) every heading in build_production_request.BLOCKS, plus the two prompt
      block headings LAYOUT AND COPY and IMAGE SLOTS;
  (e) a case-sensitive structural pattern for the numbered heading itself.

Surfaces: the visible text, produced by importing validate_public_copy's own
strip_comments and strip_tags (never a local copy of them), plus the alt, title
and aria-label attribute values, read through its own REF_ATTRS.

ALLOW RULE: a real headline is copy, a chip repeating it is an annotation. A hit
is allowed only when the same phrase occurs in <run_dir>/copy/public-copy.md AND
the page's occurrence count is not greater than the count in that file. "Second
problem" once as a headline passes; the same phrase a second time as a tab
fails. The rule applies to the structural pattern too.

Exit codes: 0 PASS; 1 FAIL (each hit printed with its line number, source class
and matched text); 2 unreadable input or a missing production-request.json.
A missing input is never a pass.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_production_request as builder  # noqa: E402  ROLE_NAMES, BLOCKS
import page_kinds  # noqa: E402  the one CTA-label reader
import validate_public_copy  # noqa: E402  strip_comments, strip_tags, REF_ATTRS, line_number
import wireframe_spec  # noqa: E402  _note

# (e) The numbered heading, exactly as SECTION_HEAD renders it, with the colon
# optional so a chip that prints "SECTION 4" alone is caught. Case-sensitive by
# design: the wireframe heading is capitals, so a sentence-case "Section" is only
# matched when it is the "Section 4 of 15" form the builder writes.
STRUCTURAL = re.compile(r"\bSECTION\s+\d{1,2}[A-C]?\b|\bSection\s+\d{1,2}[A-C]?\s+of\s+\d{1,2}\b")
NOTE_STAGES = ("desktop-wireframe", "mobile-tablet")
# The four strings _note() can return when a section supplies no behaviour note.
NOTE_FALLBACKS = ("CTA below the copy", "CTA full width below the copy",
                  "Closing CTA panel", "No CTA")
CLASS_LABEL = {
    "a": "production role name (build_production_request.ROLE_NAMES)",
    "b": "request section name (production-request.json)",
    "c": "wireframe behaviour note (wireframe_spec._note)",
    "d": "prompt block heading (build_production_request.BLOCKS)",
    "e": "numbered section heading (structural)",
}
WHOLE = lambda phrase: re.compile(  # noqa: E731  a whole-phrase, not a substring, test
    r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])", re.I)
SEP = r"(?:\s|&nbsp;|&#160;|<[^>]*>)+"


class InputError(Exception):
    """An input this validator cannot read: exit 2, never a pass."""


def norm(text) -> str:
    """Whitespace-normalised, so a phrase split across a line break still matches."""
    return " ".join(str(text or "").split())


def count_phrase(haystack: str, phrase: str) -> int:
    return len(WHOLE(phrase).findall(haystack))


def locate(html: str, phrase: str):
    """The 1-based line of the first occurrence in the original document, or None.

    The scan runs on the stripped text (the linter's own strippers); this only
    maps a matched phrase back into the file the reader opens, tolerating the
    tags and whitespace that sit between its words.
    """
    tokens = [re.escape(t) for t in phrase.split()]
    if not tokens:
        return None
    found = re.search(SEP.join(tokens), html, re.I)
    return validate_public_copy.line_number(html, found.start()) if found else None


def read_sections(run_dir: Path) -> list:
    path = run_dir / "production-request.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}")
    except ValueError as exc:
        raise InputError(f"{path} is not JSON: {exc}")
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, list) or not sections:
        raise InputError(f"{path} carries no sections list")
    return [s for s in sections if isinstance(s, dict)]


def denylist(sections: list) -> list:
    """[(class letter, phrase)] in (a)-(e) order, deduplicated on the phrase.

    Every entry comes from the module that writes it, so a new role name, block
    heading or behaviour note joins the check the moment it joins the prompt.
    """
    found, seen = [], set()

    def add(cls, phrase):
        text = norm(phrase)
        if not text or text.lower() in seen:
            return
        seen.add(text.lower())
        found.append((cls, text))

    for value in builder.ROLE_NAMES.values():
        add("a", value)
    for section in sections:
        add("b", section.get("section_name"))
    for stage in NOTE_STAGES:
        for section in sections:
            cta = page_kinds.cta_label(section)
            for closing in (False, True):
                add("c", wireframe_spec._note(stage, section, cta, None, closing))
    for value in NOTE_FALLBACKS:
        add("c", value)
    for _key, heading in builder.BLOCKS:
        add("d", heading)
    for heading in ("LAYOUT AND COPY", "IMAGE SLOTS"):
        add("d", heading)
    return found


def scan_surfaces(html: str):
    """(visible text, [(attribute value, ...)]), through the linter's own readers."""
    no_comments = validate_public_copy.strip_comments(html)
    visible = validate_public_copy.strip_tags(no_comments)
    attrs = [validate_public_copy.unquote(m.group(1))
             for m in validate_public_copy.REF_ATTRS.finditer(no_comments)]
    return visible, attrs


def hits(html: str, sections: list, copy_text: str) -> list:
    """Every annotation on the page that the ALLOW RULE does not excuse."""
    visible, attrs = scan_surfaces(html)
    page = norm(visible) + " " + norm(" ".join(attrs))
    copy = norm(copy_text)
    found = []
    for cls, phrase in denylist(sections):
        on_page = count_phrase(page, phrase)
        if not on_page:
            continue
        in_copy = count_phrase(copy, phrase)
        if in_copy and on_page <= in_copy:
            continue  # a real headline, printed no more often than the copy prints it
        found.append((cls, phrase, locate(html, phrase), on_page, in_copy))
    for phrase in dict.fromkeys(m.group(0) for m in STRUCTURAL.finditer(page)):
        on_page = len([m for m in STRUCTURAL.finditer(page) if m.group(0) == phrase])
        in_copy = len([m for m in STRUCTURAL.finditer(copy) if m.group(0) == phrase])
        if in_copy and on_page <= in_copy:
            continue
        found.append(("e", phrase, locate(html, phrase), on_page, in_copy))
    return found


def audit(html_path: Path, run_dir: Path):
    """(exit code, [report lines]) for one page. Raises InputError on bad input."""
    try:
        html = Path(html_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {html_path}: {exc}")
    sections = read_sections(Path(run_dir))
    copy_path = Path(run_dir) / "copy" / "public-copy.md"
    try:
        copy_text = copy_path.read_text(encoding="utf-8")
    except OSError as exc:  # the ALLOW RULE cannot be evaluated, so nothing may pass
        raise InputError(f"cannot read {copy_path}: {exc}")
    found = hits(html, sections, copy_text)
    if not found:
        return 0, [f"PASS {html_path}: no production annotation reached the page."]
    lines = [f"FAIL {html_path}: {len(found)} production annotation(s) reached the page."]
    for cls, phrase, line, on_page, in_copy in found:
        where = f"line {line}" if line else "line unknown"
        lines.append(f"- {where}: ({cls}) {CLASS_LABEL[cls]}: {phrase!r} "
                     f"(on the page {on_page}x, in copy/public-copy.md {in_copy}x)")
    return 1, lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail a built page carrying wireframe/build annotations (chips, name tabs, "
                    "type-spec labels, behaviour notes, numbered section headings).")
    parser.add_argument("html_path", type=Path, help="the built page or mockup HTML to scan")
    parser.add_argument("--run-dir", type=Path, required=True,
                        help="the run: its production-request.json and copy/public-copy.md supply "
                             "the denylist and the ALLOW RULE")
    args = parser.parse_args(argv)
    try:
        code, lines = audit(args.html_path, args.run_dir)
    except InputError as exc:
        print(f"CANNOT CHECK: {exc}")
        return 2
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
