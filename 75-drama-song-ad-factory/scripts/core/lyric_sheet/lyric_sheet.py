#!/usr/bin/env python3
"""DEL-09: the LYRIC SHEET PDF - the approved song words as a bright handout.

Every delivery folder carries a lyric sheet. The words come from the APPROVED
``creative/script.json`` the run already holds - the same sheet the client
approved and the music request was built from - quoted, never rewritten, and
the section breaks are the song's own tagged blocks, so the sheet reads in the
order the song runs.

Look, matching the approved client guide: white page, near-black ink, a gold
rule under the heading, section rules between blocks, generous leading, and
NOTHING on the page below ``MIN_PT`` (12 pt), footer included.

Standard library only - this skill's core is stdlib-only, so the PDF writer
lives here instead of in a package. No date, no random id: the same approved
sheet renders byte for byte the same, every run.

Page law: this module never adds a price, an income promise or a tool/model
name. ``TOOL_NAMES`` are refused fail-closed over the finished page text, and
the chrome strings are checked for money wording. The client's own approved
title and lyric lines are printed verbatim as the quotation they are.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from lyric_writer import lyric_structure as _LS  # noqa: E402  (one sheet parse)

TOOL_NAME = "lyric_sheet"
TOOL_VERSION = "1.0.0"

#: the numbered name this package item carries in the delivery folder
SLOT = "09"
FILE_NAME = "%s - Lyric Sheet.pdf" % SLOT

#: nothing on a client-facing page may be smaller than this
MIN_PT = 12.0

PAGE_W, PAGE_H = 612.0, 792.0            # US Letter, points
MARGIN = 64.0
TOP = 62.0
BOTTOM = 78.0
FOOTER_Y = 46.0
CONTENT_W = PAGE_W - 2 * MARGIN

INK = (0.10, 0.10, 0.12)                 # near-black body ink
ACCENT = (0.66, 0.45, 0.11)              # the guide's gold, for rules
ACCENT_INK = (0.50, 0.33, 0.06)          # darker gold: type stays legible
MUTED = (0.36, 0.36, 0.40)               # subtitle + footer
RULE = (0.82, 0.82, 0.85)

EYEBROW = "LYRIC SHEET"
SUBTITLE = "The approved words of this song, in the order they are sung."
FOOTER_TEXT = "page %d of %d"
INSTRUMENTAL_NOTE = "Instrumental - no words in this section."

#: chrome this module writes may carry no money wording and no income promise
_MONEY_RE = re.compile(r"\$\s*\d|€\s*\d|\bUSD\b|\bfree money\b|\bpassive income\b"
                       r"|\bincome promise\b|\bguaranteed income\b", re.I)

#: no tool or model name may reach a client-facing page. Word tokens only -
#: a bare "kie" catches the host too (\\bkie\\b splits on the dot), and no
#: host spelling ever lands in core where F14's qc-no-direct-kie.sh scans.
TOOL_NAMES = ("anthropic", "claude", "chatgpt", "gpt", "openai", "openrouter",
              "ollama", "suno", "kie", "deepseek", "moonshot",
              "minimax", "kling", "seedance", "veo", "gemini", "reportlab",
              "pypdf", "ffmpeg", "whisper")

# ---- base-14 Helvetica widths (1000 units/em), ASCII 32..126 -------------
_W_REG = (278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333,
          278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278,
          584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
          500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
          667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556,
          278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
          278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584)
_W_BOLD = (278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333,
           278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333,
           584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278,
           556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
           667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556,
           333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556,
           333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584)
_W_OBL = (278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333,
          278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278,
          584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
          500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
          667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556,
          278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
          278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584)
_FONTS = (("F1", _W_REG), ("F2", _W_BOLD), ("F3", _W_OBL))
_WIDE = 778                       # conservative width for any char >= 128

#: typographic characters the client's own words may carry
_FOLD = {"‘": "'", "’": "'", "“": '"', "”": '"',
         "–": "-", "—": " - ", "…": "...", " ": " ",
         "•": "-", "…": "..."}


class LyricSheetError(Exception):
    """Fail closed with a code the caller can show."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _san(text):
    """Printable WinAnsi text: smart punctuation folded, the rest latin-1."""
    s = str(text)
    for bad, good in _FOLD.items():
        s = s.replace(bad, good)
    out = []
    for ch in s:
        o = ord(ch)
        out.append(ch if o < 128 or 0xA0 <= o <= 0xFF else "?")
    return "".join(out)


def text_width(text, pt, font="F1"):
    """Width in points of ``text`` at ``pt`` in one of the three fonts."""
    widths = dict(_FONTS)[font]
    total = 0
    for ch in _san(text):
        o = ord(ch)
        total += widths[o - 32] if 32 <= o <= 126 else _WIDE
    return total * pt / 1000.0


def wrap(text, pt, max_w, font="F1"):
    """Greedy word wrap: every returned line is at most ``max_w`` wide."""
    words = _san(text).split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for word in words[1:]:
        trial = "%s %s" % (cur, word)
        if text_width(trial, pt, font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    # a single word wider than the column still has to fit: hard-cut it
    out = []
    for line in lines:
        while text_width(line, pt, font) > max_w and len(line) > 1:
            cut = len(line)
            while cut > 1 and text_width(line[:cut], pt, font) > max_w:
                cut -= 1
            out.append(line[:cut])
            line = line[cut:]
        out.append(line)
    return out


def _esc(text):
    """PDF literal-string body (WinAnsi bytes arrive as latin-1)."""
    s = _san(text)
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Canvas:
    """Pages of content-stream operators, cursor from the top, no fills."""

    def __init__(self):
        self.pages = []
        self.ops = []
        self.texts = []
        self.y = PAGE_H - TOP

    def new_page(self):
        if self.ops:
            self.pages.append(self.ops)
        self.ops = []
        self.y = PAGE_H - TOP

    def need(self, height):
        if self.y - height < BOTTOM:
            self.new_page()

    def text(self, s, font, pt, color, leading, x=MARGIN):
        if pt < MIN_PT:
            raise LyricSheetError("BELOW_MIN_PT",
                                  "%s pt is under the 12 pt floor" % pt)
        r, g, b = color
        body = _esc(s)
        self.ops.append(
            "BT /%s %.1f Tf %.3f %.3f %.3f rg %.2f %.2f Td (%s) Tj ET"
            % (font, pt, r, g, b, x, self.y, body))
        self.texts.append(s)
        self.y -= leading

    def paragraph(self, s, font, pt, color, leading, x=MARGIN, width=CONTENT_W):
        for line in wrap(s, pt, width, font):
            self.need(leading)
            self.text(line, font, pt, color, leading, x)

    def rule(self, color, thickness=1.0, y=None, x0=MARGIN, x1=None):
        y = self.y if y is None else y
        x1 = (PAGE_W - MARGIN) if x1 is None else x1
        r, g, b = color
        self.ops.append("q %.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S Q"
                        % (r, g, b, thickness, x0, y, x1, y))

    def space(self, gap):
        self.y -= gap

    def footers(self, total):
        for i, ops in enumerate(self.pages, 1):
            r, g, b = MUTED
            label = FOOTER_TEXT % (i, total)
            x = (PAGE_W - text_width(label, MIN_PT, "F1")) / 2.0
            ops.append("BT /F1 %.1f Tf %.3f %.3f %.3f rg %.2f %.2f Td (%s) Tj ET"
                       % (MIN_PT, r, g, b, x, FOOTER_Y, _esc(label)))
            self.texts.append(label)

    def finish(self):
        if self.ops:
            self.pages.append(self.ops)
            self.ops = []
        self.footers(len(self.pages))
        return self.pages


# ---- the approved sheet ---------------------------------------------------

def load_script(run_dir):
    """The run's approved ``creative/script.json``; fail closed if unreadable."""
    path = os.path.join(os.path.abspath(run_dir), "creative", "script.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise LyricSheetError("SCRIPT_MISSING",
                              "no approved script at %s" % path) from None
    except (OSError, ValueError) as exc:
        raise LyricSheetError("SCRIPT_UNREADABLE", str(exc)) from None
    if not isinstance(data, dict):
        raise LyricSheetError("SCRIPT_UNREADABLE", "script.json is not an object")
    return data


def sections_of(script):
    """The song's own blocks: ``[{"tag", "lines"}]`` in song order.

    Uses the approved ``sheet`` when the run carries one; otherwise parses the
    approved ``lyrics`` text through the shared ``lyric_structure.parse_sheet``
    so both paths give the same section structure. No block, no words: refuse.
    """
    if not isinstance(script, dict):
        raise LyricSheetError("SCRIPT_UNREADABLE", "script must be an object")
    sheet = script.get("sheet")
    if isinstance(sheet, list) and sheet:
        blocks = []
        for raw in sheet:
            if not isinstance(raw, dict):
                raise LyricSheetError("SHEET_UNREADABLE",
                                      "a sheet block must be an object")
            lines = [str(x) for x in (raw.get("lines") or [])
                     if str(x).strip()]
            blocks.append({"tag": _san(raw.get("tag") or "").strip(),
                           "lines": lines})
        if any(b["lines"] for b in blocks):
            return blocks
    text = script.get("lyrics")
    if not isinstance(text, str) or not text.strip():
        raise LyricSheetError("EMPTY_SHEET",
                              "the approved script carries no lyric words")
    try:
        blocks = _LS.parse_sheet(text)
    except Exception as exc:                       # noqa: BLE001 - parser refusal
        raise LyricSheetError("EMPTY_SHEET", str(exc)) from None
    if not blocks:
        raise LyricSheetError("EMPTY_SHEET", "the approved sheet has no sections")
    return [{"tag": _san(b.get("tag") or "").strip(),
             "lines": [str(x) for x in (b.get("lines") or []) if str(x).strip()]}
            for b in blocks]


def _label(tag):
    """Section heading from the song's own tag: 'pre-chorus' -> 'Pre-Chorus'."""
    return tag.strip().title() or "Song"


def _chrome_clean(strings):
    for s in strings:
        if _MONEY_RE.search(s):
            raise LyricSheetError("MONEY_ON_PAGE",
                                  "chrome carries money wording: %s" % s)
    return True


def _no_tool_names(strings):
    joined = " \n".join(strings)
    for name in TOOL_NAMES:
        if re.search(r"\b%s\b" % re.escape(name), joined, re.I):
            raise LyricSheetError("TOOL_NAME_ON_PAGE",
                                  "a tool or model name reached the page: %s"
                                  % name.upper())
    return True


# ---- the page -------------------------------------------------------------

def build_pdf(script, out_path):
    """Render the approved sheet to ``out_path``; returns a JSON-safe receipt."""
    title = _san((script or {}).get("title") or "Your song").strip() or "Your song"
    sections = sections_of(script)
    chrome = [EYEBROW, SUBTITLE, INSTRUMENTAL_NOTE,
              FOOTER_TEXT % (1, 1)]
    _chrome_clean(chrome)

    c = _Canvas()
    c.text(EYEBROW, "F2", MIN_PT, ACCENT_INK, 26.0)
    c.paragraph(title, "F2", 26.0, INK, 31.0)
    c.space(4.0)
    c.paragraph(SUBTITLE, "F3", 13.0, MUTED, 17.0)
    c.space(16.0)
    c.rule(ACCENT, 1.6)
    c.space(30.0)

    line_count = 0
    for index, block in enumerate(sections):
        if index:                                  # a real section break
            c.space(24.0)
        c.need(74.0)                               # header + first line stay up
        c.text(_label(block["tag"]), "F2", 15.0, ACCENT_INK, 20.0)
        c.rule(RULE, 0.8)
        c.space(15.0)
        if not block["lines"]:
            c.paragraph(INSTRUMENTAL_NOTE, "F3", 13.0, MUTED, 18.0)
            continue
        for line in block["lines"]:
            c.paragraph(line, "F1", 13.0, INK, 19.0)
            line_count += 1
        c.space(6.0)

    pages = c.finish()
    _no_tool_names(c.texts)

    payload = _objects(pages)
    target = os.path.abspath(out_path)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(payload)
    size = os.path.getsize(target)
    if size < 512:
        raise LyricSheetError("PDF_NOT_WRITTEN", "%s is only %d bytes"
                              % (target, size))
    return {"file": target, "name": os.path.basename(target),
            "pages": len(pages), "sections": len(sections),
            "lines": line_count, "bytes": size, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION}


def _stream(ops):
    body = "\n".join(ops).encode("latin-1")
    return b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"


def _objects(pages):
    """The whole file: header, objects, xref, trailer (deterministic order)."""
    objs = {}
    n_pages = len(pages)
    font_ids = {"F1": 3, "F2": 4, "F3": 5}
    base = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Helvetica-Oblique"}
    kids = " ".join("%d 0 R" % (6 + i) for i in range(n_pages))
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n_pages)
               ).encode("latin-1")
    for name, ident in font_ids.items():
        objs[ident] = ("<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                       "/Encoding /WinAnsiEncoding >>" % base[name]
                       ).encode("latin-1")
    for i, ops in enumerate(pages):
        page_id = 6 + i
        content_id = 6 + n_pages + i
        objs[page_id] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.0f %.0f] "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
            "/Contents %d 0 R >>" % (PAGE_W, PAGE_H, content_id)
        ).encode("latin-1")
        objs[content_id] = _stream(ops)

    out = bytearray()
    offsets = {}
    out += b"%PDF-1.4\n"
    for ident in sorted(objs):
        offsets[ident] = len(out)
        out += b"%d 0 obj\n" % ident
        out += objs[ident]
        out += b"\nendobj\n"
    xref_at = len(out)
    count = max(objs) + 1
    out += b"xref\n0 %d\n" % count
    out += b"0000000000 65535 f \n"
    for ident in range(1, count):
        out += b"%010d 00000 n \n" % offsets[ident]
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (count, xref_at))
    return bytes(out)


def write_delivery(run_dir, delivery_dir=None):
    """Build the sheet into the run's delivery folder under its numbered name."""
    script = load_script(run_dir)
    out_dir = delivery_dir or os.path.join(os.path.abspath(run_dir), "delivery")
    os.makedirs(out_dir, exist_ok=True)
    receipt = build_pdf(script, os.path.join(out_dir, FILE_NAME))
    receipt["delivery_dir"] = os.path.abspath(out_dir)
    return receipt


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        prog="lyric_sheet", description="DEL-09: lyric sheet PDF for one run")
    parser.add_argument("--run", required=True,
                        help="run folder holding creative/script.json")
    parser.add_argument("--out", default=None,
                        help="delivery folder (default: <run>/delivery)")
    ns = parser.parse_args(argv)
    try:
        receipt = write_delivery(ns.run, ns.out)
    except LyricSheetError as exc:
        json.dump({"outcome": "error", "code": exc.code, "detail": exc.message},
                  sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 1
    receipt["outcome"] = "ok"
    json.dump(receipt, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0




def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: the REAL DEL-09 deliver path (lyric sheet).

    Calls ``write_delivery(run_dir, delivery_dir)`` -- the same entry the
    CLI runs: it loads the run's approved ``creative/script.json`` and lays
    every word of the song out under the numbered name. Fixture bytes are
    never written: ``contract.produce_item`` is test-only and no deliver
    path imports it. Signature: produce_delivery(run_dir, item) -> list[Path].
    """
    from delivery_package import run_inputs as RI
    out = RI.delivery_dir(run_dir)
    write_delivery(str(run_dir), str(out))
    return RI.stage(item, out)

if __name__ == "__main__":
    sys.exit(main())
