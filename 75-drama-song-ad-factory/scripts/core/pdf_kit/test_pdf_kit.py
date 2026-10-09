#!/usr/bin/env python3
"""pdf_kit: the delivery-PDF writer's own contract.

Proves the three rules every client document depends on: the 12 pt floor
refuses, PNG stills decode (alpha composited onto the white page), and a saved
file is a structurally valid PDF whose text can be read back for QC scans.

Run: python3 scripts/core/pdf_kit/test_pdf_kit.py   (stdlib only, no network)
"""
import os
import struct
import sys
import tempfile
import zlib

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import pdf_kit.pdf_kit as P   # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        "" if cond else " (%s)" % (detail,)))
    if not cond:
        FAILS.append(name)


def png_bytes(width, height, pixel, colour=6, interlace=0):
    """An 8-bit PNG. colour 6 = RGBA, 2 = RGB; interlace 1 = Adam7."""
    rows = b""
    for _ in range(height):
        rows += b"\x00" + bytes(pixel) * width
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, interlace)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def jpeg_stub(width, height, components=3):
    """Just enough JPEG SOF0 marker for _jpeg_size (no picture data)."""
    return (b"\xff\xd8\xff\xc0"
            + struct.pack(">HBHHB", 8 + 3 * components, 8, height, width,
                          components)
            + b"".join(bytes([i, 0x11, 0]) for i in range(components))
            + b"\xff\xd9")


def test_width_and_wrap():
    one = P.text_width("i", "Helvetica", 12)
    check("a narrow glyph is narrow", 0 < one < 4, one)
    check("bold is wider than regular", P.text_width("Warm", "Helvetica-Bold", 12)
          > P.text_width("Warm", "Helvetica", 12))
    lines = P.wrap("the quick brown fox jumps over the lazy dog", "Helvetica",
                   12, 90)
    check("wrap produced more than one line", len(lines) > 1, lines)
    check("no wrapped line overflows",
          all(P.text_width(l, "Helvetica", 12) <= 90 for l in lines),
          [P.text_width(l, "Helvetica", 12) for l in lines])
    check("wrap keeps every word", " ".join(lines).split()
          == "the quick brown fox jumps over the lazy dog".split())
    long_word = P.wrap("supercalifragilisticexpialidocious", "Helvetica", 12, 40)
    check("an oversized token is hard-split",
          len(long_word) > 1 and all(
              P.text_width(l, "Helvetica", 12) <= 40 for l in long_word),
          long_word)
    check("block_height matches the drawn lines",
          P.block_height("two words here", 500, "Helvetica", 12, 15)
          == 15, P.block_height("two words here", 500, "Helvetica", 12, 15))
    assert not FAILS, FAILS


def test_font_floor():
    for size in (6, 9, 11, 11.999):
        try:
            P.text_width("x", "Helvetica", size)
            check("width refuses %s pt" % size, False)
        except P.PdfError as exc:
            check("width refuses %s pt" % size, exc.code == "FONT_TOO_SMALL",
                  exc)
    doc = P.Canvas()
    doc.new_page()
    try:
        doc.text(72, 700, "too small", size=11)
        check("draw refuses under 12 pt", False)
    except P.PdfError as exc:
        check("draw refuses under 12 pt", exc.code == "FONT_TOO_SMALL", exc)
    try:
        doc.text_block(72, 700, "too small", 200, size=10)
        check("block refuses under 12 pt", False)
    except P.PdfError as exc:
        check("block refuses under 12 pt", exc.code == "FONT_TOO_SMALL", exc)
    doc.text(72, 700, "exactly the floor", size=12)
    check("12 pt is allowed", True)
    assert not FAILS, FAILS


def test_png_decode():
    data = png_bytes(3, 2, (10, 20, 30, 255))
    w, h, rgb = P._png(data)
    check("RGB(A) dimensions", (w, h) == (3, 2), (w, h))
    check("opaque pixel keeps its colour", rgb[:3] == bytes((10, 20, 30)), rgb[:6])
    check("packed RGB is 3 bytes a pixel", len(rgb) == 3 * 2 * 3, len(rgb))

    clear = png_bytes(2, 1, (255, 0, 0, 0))     # fully transparent red
    _, _, flat = P._png(clear)
    check("transparent pixel composites onto the white page",
          flat[:3] == bytes((255, 255, 255)) and len(flat) == 6, flat)

    half = png_bytes(1, 1, (0, 0, 0, 128))      # half-transparent black
    _, _, mid = P._png(half)
    check("half alpha lands mid-grey, not black",
          all(110 <= b <= 145 for b in mid), mid)

    try:
        P._png(b"not a png at all")
        check("foreign image refused", False)
    except P.PdfError as exc:
        check("foreign image refused", exc.code == "PNG_UNSUPPORTED", exc)

    try:
        P._png(png_bytes(2, 2, (1, 2, 3, 255), interlace=1))
        check("interlaced PNG refused by name", False)
    except P.PdfError as exc:
        check("interlaced PNG refused by name", exc.code == "PNG_INTERLACED",
              exc)
    assert not FAILS, FAILS


def test_jpeg_probe():
    w, h, comps = P._jpeg_size(jpeg_stub(640, 360, 3))
    check("jpeg frame size read", (w, h, comps) == (640, 360, 3), (w, h, comps))
    try:
        P._jpeg_size(jpeg_stub(8, 8, 4))
        check("4-component jpeg refused", False)
    except P.PdfError as exc:
        check("4-component jpeg refused", exc.code == "JPEG_UNSUPPORTED", exc)
    try:
        P._jpeg_size(b"\x89PNG\r\n\x1a\n")
        check("non-jpeg refused by the jpeg probe", False)
    except P.PdfError as exc:
        check("non-jpeg refused by the jpeg probe",
              exc.code == "JPEG_UNSUPPORTED", exc)
    assert not FAILS, FAILS


def test_save_round_trip():
    tmp = tempfile.mkdtemp(prefix="pdfkit-")
    still = os.path.join(tmp, "still.png")
    with open(still, "wb") as fh:
        fh.write(png_bytes(64, 36, (90, 140, 200, 255)))
    doc = P.Canvas()
    doc.new_page()
    doc.text(72, 720, "Storyboard", font="Helvetica-Bold", size=20)
    doc.image(still, 72, 500, 260, 146)
    doc.text_block(72, 480, "A caption that wraps across the box width.",
                   260)
    doc.new_page()
    doc.text(72, 720, "Page two")
    path = doc.save(os.path.join(tmp, "out.pdf"))
    blob = open(path, "rb").read()
    check("header", blob.startswith(b"%PDF-1.4"), blob[:8])
    check("trailer closed", blob.rstrip().endswith(b"%%EOF"))
    check("cross-reference table present", b"\nxref\n" in blob)
    check("page tree counts both pages", b"/Count 2" in blob)
    check("image embedded as a Flate RGB object",
          b"/Subtype /Image" in blob and b"/FlateDecode" in blob)
    text = P.extract_text(blob)
    check("drawn text read back", "Storyboard" in text, text)
    check("second page read back", "Page two" in text, text)
    check("wrapping happened", "wraps across the box" in text, text)
    try:
        P.Canvas().save(os.path.join(tmp, "empty.pdf"))
        check("empty document refused", False)
    except P.PdfError as exc:
        check("empty document refused", exc.code == "EMPTY_DOCUMENT", exc)
    assert not FAILS, FAILS


def test_extract_skips_image_bytes():
    tmp = tempfile.mkdtemp(prefix="pdfkit-")
    still = os.path.join(tmp, "s.png")
    with open(still, "wb") as fh:
        fh.write(png_bytes(8, 8, (255, 0, 0, 255)))
    doc = P.Canvas()
    doc.new_page()
    doc.text(72, 720, "Only the caption")
    doc.image(still, 72, 500, 72, 72)
    text = P.extract_text(open(doc.save(os.path.join(tmp, "x.pdf")), "rb").read())
    check("caption text only", text.strip() == "Only the caption", repr(text))
    assert not FAILS, FAILS


if __name__ == "__main__":
    for run in (test_width_and_wrap, test_font_floor, test_png_decode,
                test_jpeg_probe, test_save_round_trip,
                test_extract_skips_image_bytes):
        run()
    print("FAIL (%d): %s" % (len(FAILS), ", ".join(FAILS)) if FAILS
          else "ALL PASS")
    sys.exit(1 if FAILS else 0)
