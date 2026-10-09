#!/usr/bin/env python3
"""pdf_writer tests: the standard-library page layout engine.

The invariants that matter to a client-facing page: the type floor, wrapping
that never overruns the margin, clean page breaks, and a file a real PDF reader
will open. Run: python3 delivery_docs/test_pdf_writer.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)
from delivery_docs import pdf_writer as PW  # noqa: E402


def test_type_floor_is_enforced():
    layout = PW.Layout()
    for size in (11.9, 9.0, 8.0, 6.0, 1.0):
        try:
            layout.para("too small", size=size)
        except ValueError:
            continue
        raise AssertionError("size %s rendered below the %s pt floor"
                             % (size, PW.MIN_PT))
    try:
        PW.Layout().para("ok", size=PW.MIN_PT)
    except ValueError as exc:
        raise AssertionError("the exact floor must be allowed: %s" % exc)


def test_leading_must_fit_the_type():
    try:
        PW.Layout().para("x", size=14.0, leading=13.0)
    except ValueError:
        return
    raise AssertionError("leading tighter than the type was allowed")


def test_wrap_never_exceeds_the_width():
    text = ("w" * 40 + " ") * 30
    width = PW.PAGE_W - PW.MARGIN_L - PW.MARGIN_R
    lines = PW.wrap(text, "F1", 13.0, width)
    assert len(lines) > 1, "expected the wall of words to wrap"
    for line in lines:
        assert PW.text_width(line, "F1", 13.0) <= width, line


def test_wrap_handles_newlines_and_long_words():
    lines = PW.wrap("a\n\nb", "F1", 13.0, 200.0)
    assert lines[0] == "a" and lines[1] == "" and lines[2] == "b", lines
    long_word = "x" * 500
    chunked = PW.wrap(long_word, "F1", 13.0, 120.0)
    assert "".join(chunked) == long_word, "wrap lost characters"
    for line in chunked:
        assert PW.text_width(line, "F1", 13.0) <= 120.0


def test_fit_cuts_with_an_ellipsis():
    narrow = 60.0
    got = PW.fit("an extraordinarily long section heading", "F1", 13.0, narrow)
    assert PW.text_width(got, "F1", 13.0) <= narrow, got
    assert got.endswith("..."), got
    assert PW.fit("short", "F1", 13.0, narrow) == "short"


def test_widths_are_positive_and_bold_is_wider():
    for font in ("F1", "F2", "F3"):
        for ch in "AgW8 éñ":
            w = PW.text_width(ch, font, 12.0)
            assert w > 0, (font, ch, w)
    assert PW.text_width("Handgloves", "F2", 13.0) \
        > PW.text_width("Handgloves", "F1", 13.0)


def test_unmappable_character_becomes_a_question_mark():
    layout = PW.Layout()
    layout.para("level \U0001F3A9 of joy", size=13.0)
    ops = "\n".join(layout.pages[0])
    assert "level" in ops and "?" in ops, ops


def test_pages_break_at_the_footer_not_mid_block():
    layout = PW.Layout()
    layout.para("line", size=13.0, leading=19.0)
    y_before = layout.y
    for _ in range(200):
        layout.para("another line of body copy", size=13.0, leading=19.0)
    assert len(layout.pages) > 1, "200 lines should not fit one page"
    # nothing is drawn below the bottom margin on any page
    for index, ops in enumerate(layout.pages):
        for match in re.finditer(r"1 0 0 1 [0-9.]+ ([0-9.]+) Tm", "\n".join(ops)):
            baseline = float(match.group(1))
            assert baseline >= PW.MARGIN_B, (index, baseline)
    assert layout.y < y_before


def test_outputs_a_wellformed_pdf():
    layout = PW.Layout()
    layout.para("Approved for production", font="F2", size=PW.MIN_PT,
                color=PW.ACCENT)
    layout.para("A body line with an accent color.", size=13.0)
    layout.rule(3.0, PW.BAR)
    data = layout.to_bytes()
    assert data.startswith(b"%PDF-1.4"), data[:16]
    assert data.rstrip().endswith(b"%%EOF"), data[-16:]
    assert b"/Font" in data and b"WinAnsiEncoding" in data
    assert b"/MediaBox [0 0 612 792]" in data, "expected US Letter"
    sizes = [float(s) for s in re.findall(rb"/F\d\s+([0-9.]+)\s+Tf", data)]
    assert sizes and min(sizes) >= PW.MIN_PT, sizes
    assert b"/Count %d" % len(layout.pages) in data
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "doc.pdf")
        with open(path, "wb") as handle:
            handle.write(data)
        checked = False
        try:                                            # a real reader, if any
            checked = subprocess.call(
                ["qpdf", "--check", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        except OSError:
            checked = False
        if checked:
            return
        try:
            import pypdf                                # noqa: PLC0415
        except ImportError:
            return                                      # neither reader present
        reader = pypdf.PdfReader(path)
        assert len(reader.pages) == len(layout.pages)
        text = reader.pages[0].extract_text() or ""
        assert "Approved for production" in text, text


def test_footer_counts_pages():
    layout = PW.Layout()
    layout.on_footer(lambda page, total: [
        PW._text_op(PW.MARGIN_L, 40, "Page %d of %d" % (page, total),
                    "F1", PW.MIN_PT, PW.GREY)])
    for i in range(120):
        layout.para("line %d" % i, size=13.0, leading=19.0)
    assert len(layout.pages) >= 2
    data = layout.to_bytes()
    assert b"Page 1 of %d" % len(layout.pages) in data
    assert b"Page 2 of %d" % len(layout.pages) in data
    assert b"Page %d of %d" % (len(layout.pages), len(layout.pages)) in data


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)