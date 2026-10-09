#!/usr/bin/env python3
"""pdf_kit.py: the shared standard-library PDF writer for the delivery package.

One writer every client-facing delivery PDF (DEL-01..DEL-12) composes with, so
the approved client-guide look is built once and never re-invented per document.

Rules it enforces for every caller, not just this one:
  * every font size below MIN_PT raises FONT_TOO_SMALL -- nothing under 12 pt
    ever reaches a page;
  * the page background is white and the default text colour is near-black, so
    a document stays bright in print and on a phone;
  * no third-party dependency: the CI suite runs each test file under a fresh
    empty HOME with stock python3 (numpy/opencv are installed for other suites
    only), so reportlab/fpdf/weasyprint are not available to rely on.

How it draws: base-14 Helvetica (no font embedding) with the real AFM advance
widths carried here, so word wrap is exact instead of estimated. JPEG is
embedded unchanged as DCTDecode. PNG is decoded in this module (zlib + the five
scanline filters) and re-flated as raw RGB with its alpha composited onto
white -- a still with transparent corners must not print as a black hole.

Standard library only. No network, no spend, no absolute operator path.
"""
from __future__ import annotations

import re
import struct
import zlib

#: Nothing a client reads may be set below this (Trevor, DEL package).
MIN_PT = 12.0
#: Default body size and line leading.
BODY_PT = 12.0
LEADING = 1.42

PAGE_W = 612.0            # US Letter, portrait (points)
PAGE_H = 792.0
MARGIN = 36.0

#: RGB, 0.0-1.0. Bright page, dark type, one warm accent -- the client-guide look.
PAPER = (1.0, 1.0, 1.0)
INK = (0.12, 0.13, 0.16)
MUTED = (0.36, 0.38, 0.43)
RULE = (0.85, 0.86, 0.89)
ACCENT = (0.72, 0.53, 0.13)

#: Helvetica advance widths per 1000 units for ASCII 32..126 (AFM).
_REG = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333,
        278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278,
        584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
        500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
        667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556,
        278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
        278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333,
         278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333,
         584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278,
         556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
         667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556,
         333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556,
         333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]

#: font name -> resource key, widths. Oblique carries the regular widths.
FONTS = {
    "Helvetica": ("F1", _REG),
    "Helvetica-Bold": ("F2", _BOLD),
    "Helvetica-Oblique": ("F3", _REG),
}
_FONT_ORDER = ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique")

_QUESTION = 556   # width of "?" -- the fallback for a character outside ASCII


class PdfError(Exception):
    """Named, fail-closed refusal (code carries the machine-readable part)."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _widths(font):
    try:
        return FONTS[font][1]
    except KeyError:
        raise PdfError("FONT_UNKNOWN", "no such base font: %r" % (font,))


def _check_size(size):
    if float(size) < MIN_PT:
        raise PdfError("FONT_TOO_SMALL",
                       "%s pt is under the %s pt floor" % (size, MIN_PT))
    return float(size)


def text_width(text, font="Helvetica", size=BODY_PT):
    """Rendered advance width of ``text`` in points (exact AFM sum).

    Honours the 12 pt floor too: a caller that measures has already decided to
    draw, and the floor must not be reachable by measuring first.
    """
    size = _check_size(size)
    table = _widths(font)
    total = 0
    for ch in str(text):
        o = ord(ch)
        total += table[o - 32] if 32 <= o < 127 else _QUESTION
    return total * size / 1000.0


def wrap(text, font="Helvetica", size=BODY_PT, max_width=100.0):
    """Greedy word wrap; a word wider than the box is hard-split so it fits."""
    size = _check_size(size)
    words = str(text).split()
    if not words:
        return [""]
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(trial, font, size) <= max_width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        if text_width(word, font, size) <= max_width:
            cur = word
            continue
        piece = ""
        for ch in word:                      # one long token: break by character
            if text_width(piece + ch, font, size) <= max_width:
                piece += ch
            else:
                if piece:
                    lines.append(piece)
                piece = ch
        cur = piece
    if cur:
        lines.append(cur)
    return lines or [""]


def block_height(text, max_width, font="Helvetica", size=BODY_PT,
                 leading=None):
    """Height a wrapped block of ``text`` occupies (for layout before drawing)."""
    size = _check_size(size)
    lead = float(leading) if leading else size * LEADING
    return len(wrap(text, font, size, max_width)) * lead


def _esc(text):
    raw = str(text).encode("cp1252", "replace")
    out = bytearray()
    for b in raw:
        if b in (0x28, 0x29, 0x5C):          # ( ) \
            out.append(0x5C)
        out.append(b)
    return bytes(out).decode("latin-1")


def _rgb(color):
    r, g, b = color
    return "%.3f %.3f %.3f" % (r, g, b)


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------

def _jpeg_size(data):
    """(width, height, components) from a JPEG SOF marker."""
    if data[:2] != b"\xff\xd8":
        raise PdfError("JPEG_UNSUPPORTED", "not a JPEG stream")
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 4 > len(data):
            break
        seglen = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 9 > len(data):
                break
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            comps = data[i + 9]
            if comps not in (1, 3):
                raise PdfError("JPEG_UNSUPPORTED",
                               "%d-component JPEG is not embeddable" % comps)
            return w, h, comps
        if seglen < 2:
            break
        i += 2 + seglen
    raise PdfError("JPEG_UNSUPPORTED", "no JPEG frame header found")


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_PAETH = lambda a, b, c: (                          # noqa: E731
    a if abs(b - c) <= abs(a - c) and abs(b - c) <= abs(a - b)
    else (b if abs(a - c) <= abs(a - b) else c))


def _unfilter(raw, stride, bpp, height):
    """Reverse the five PNG scanline filters; returns raw scanline bytes."""
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        if pos + 1 + stride > len(raw):
            raise PdfError("PNG_TRUNCATED", "image data ends mid-scanline")
        ft = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ft == 1:                                # Sub
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + left) & 0xFF
        elif ft == 2:                              # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:                              # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:                              # Paeth
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up = prev[i]
                ul = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _PAETH(left, up, ul)) & 0xFF
        elif ft != 0:
            raise PdfError("PNG_UNSUPPORTED", "unknown filter %d" % ft)
        out += line
        prev = line
    return bytes(out)


def _over_white(c, a):
    """Composite one channel over the white page (keeps the PDF bright)."""
    return (c * a + 255 * (255 - a) + 127) // 255


def _png(data):
    """Decode a non-interlaced PNG to packed 8-bit RGB."""
    if data[:8] != _PNG_MAGIC:
        raise PdfError("PNG_UNSUPPORTED", "not a PNG stream")
    pos, idat, plte, trns, ihdr = 8, [], None, None, None
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"IDAT":
            idat.append(chunk)
        elif kind == b"PLTE":
            plte = chunk
        elif kind == b"tRNS":
            trns = chunk
        elif kind == b"IEND":
            break
    if ihdr is None:
        raise PdfError("PNG_UNSUPPORTED", "PNG has no IHDR")
    w, h, depth, ctype, comp, filt, interlace = ihdr
    if comp != 0 or filt != 0:
        raise PdfError("PNG_UNSUPPORTED", "unexpected PNG compression/filter method")
    if interlace != 0:
        # ponytail: only pass-0 PNGs; an interlaced still is converted by the
        # caller (Pillow/ffmpeg) before delivery -- Adam7 unfilter is the upgrade.
        raise PdfError("PNG_INTERLACED",
                       "interlaced PNG is not supported; re-export without interlacing")
    if ctype not in _CHANNELS:
        raise PdfError("PNG_UNSUPPORTED", "unknown PNG colour type %d" % ctype)
    if depth not in (8, 16) or (ctype == 3 and depth != 8):
        raise PdfError("PNG_UNSUPPORTED",
                       "bit depth %d with colour type %d is not supported"
                       % (depth, ctype))
    if ctype == 3 and plte is None:
        raise PdfError("PNG_UNSUPPORTED", "palette PNG has no PLTE")

    channels = _CHANNELS[ctype]
    stride = w * channels * depth // 8
    bpp = max(1, channels * depth // 8)
    pixels = _unfilter(zlib.decompress(b"".join(idat)), stride, bpp, h)

    out = bytearray(w * h * 3)
    step = depth // 8
    for y in range(h):
        row = pixels[y * stride:(y + 1) * stride]
        base = y * w * 3
        for x in range(w):
            o = base + x * 3
            if ctype == 2:
                s = x * 3 * step
                out[o] = row[s]
                out[o + 1] = row[s + step]
                out[o + 2] = row[s + 2 * step]
            elif ctype == 6:
                s = x * 4 * step
                a = row[s + 3 * step] if step == 1 else row[s + 6]
                out[o] = _over_white(row[s], a)
                out[o + 1] = _over_white(row[s + step], a)
                out[o + 2] = _over_white(row[s + 2 * step], a)
            elif ctype == 0:
                s = x * step
                g = row[s]
                out[o] = out[o + 1] = out[o + 2] = g
            elif ctype == 4:
                s = x * 2 * step
                a = row[s + step] if step == 1 else row[s + 2]
                g = row[s]
                out[o] = out[o + 1] = out[o + 2] = _over_white(g, a)
            else:                                   # ctype == 3, depth 8
                idx = row[x]
                if idx * 3 + 2 >= len(plte):
                    raise PdfError("PNG_UNSUPPORTED", "palette index out of range")
                a = trns[idx] if trns is not None and idx < len(trns) else 255
                out[o] = _over_white(plte[idx * 3], a)
                out[o + 1] = _over_white(plte[idx * 3 + 1], a)
                out[o + 2] = _over_white(plte[idx * 3 + 2], a)
    return w, h, bytes(out)


# --------------------------------------------------------------------------
# canvas
# --------------------------------------------------------------------------

class Canvas:
    """A paged vector canvas. Coordinates are points, origin bottom-left."""

    def __init__(self, width=PAGE_W, height=PAGE_H, margin=MARGIN):
        self.width = float(width)
        self.height = float(height)
        self.margin = float(margin)
        self._pages = []          # [{"ops": [...], "images": [xobject name]}]
        self._images = {}         # file path -> entry (de-duplicates re-use)
        self._by_name = {}        # xobject name -> entry

    # -- pages ------------------------------------------------------------
    @property
    def pages(self):
        return len(self._pages)

    def new_page(self, background=True):
        self._pages.append({"ops": [], "images": []})
        if background:
            self.rect(0, 0, self.width, self.height, fill=PAPER)
        return self

    def _ops(self):
        if not self._pages:
            self.new_page()
        return self._pages[-1]["ops"]

    # -- primitives -------------------------------------------------------
    def rect(self, x, y, w, h, fill=None, stroke=None, line_width=0.6):
        ops = self._ops()
        if fill is not None:
            # `rg` sets the fill colour; without it the three numbers would sit
            # on the operand stack and the rect would fill with the default
            # black -- a white page would render as a black page.
            ops.append("%s rg %.2f %.2f %.2f %.2f re f"
                       % (_rgb(fill), x, y, w, h))
        if stroke is not None:
            ops.append("%.3f w %s RG %.2f %.2f %.2f %.2f re S"
                       % (line_width, _rgb(stroke), x, y, w, h))
        return self

    def line(self, x1, y1, x2, y2, color=RULE, line_width=0.8):
        self._ops().append("%.3f w %s RG %.2f %.2f m %.2f %.2f l S"
                           % (line_width, _rgb(color), x1, y1, x2, y2))
        return self

    def text(self, x, y, s, font="Helvetica", size=BODY_PT, color=INK):
        _check_size(size)
        if not str(s):
            return self
        key = FONTS[font][0]
        self._ops().append(
            "BT /%s %.2f Tf %s rg %.2f %.2f Td (%s) Tj ET"
            % (key, size, _rgb(color), x, y, _esc(s)))
        return self

    def text_block(self, x, y_top, s, max_width, font="Helvetica",
                   size=BODY_PT, leading=None, color=INK):
        """Draw wrapped ``s`` in the box whose top edge is ``y_top``.

        The first baseline sits one ascent below ``y_top``; the return value is
        the top edge of the next free line, so blocks stack with
        ``y = block(x, y, ...)``.
        """
        size = _check_size(size)
        lead = float(leading) if leading else size * LEADING
        y = float(y_top) - size * 0.78
        for line in wrap(s, font, size, max_width):
            self.text(x, y, line, font=font, size=size, color=color)
            y -= lead
        return float(y_top) - len(wrap(s, font, size, max_width)) * lead

    def block_height(self, s, max_width, font="Helvetica", size=BODY_PT,
                     leading=None):
        """Height a ``text_block`` will consume (for layout before drawing)."""
        return block_height(s, max_width, font, size, leading)

    # -- images -----------------------------------------------------------
    def image(self, path, x, y, w, h, frame=True):
        """Fit ``path`` inside the box (x, y, w, h), preserving aspect ratio."""
        self._ops()
        entry = self._images.get(path)
        if entry is None:
            try:
                with open(path, "rb") as fh:
                    blob = fh.read()
            except OSError as exc:
                raise PdfError("IMAGE_UNREADABLE", "%s: %s" % (path, exc))
            if blob[:8] == _PNG_MAGIC:
                iw, ih, rgb = _png(blob)
                entry = {"name": "Im%d" % (len(self._images) + 1),
                         "data": zlib.compress(rgb, 9),
                         "w": iw, "h": ih, "filter": "FlateDecode",
                         "colorspace": "/DeviceRGB"}
            elif blob[:2] == b"\xff\xd8":
                iw, ih, comps = _jpeg_size(blob)
                entry = {"name": "Im%d" % (len(self._images) + 1),
                         "data": blob, "w": iw, "h": ih, "filter": "DCTDecode",
                         "colorspace": "/DeviceRGB" if comps == 3 else "/DeviceGray"}
            else:
                raise PdfError("IMAGE_UNSUPPORTED",
                               "not a PNG or JPEG: %s" % path)
            self._images[path] = entry
            self._by_name[entry["name"]] = entry
        scale = min(float(w) / entry["w"], float(h) / entry["h"])
        dw, dh = entry["w"] * scale, entry["h"] * scale
        dx = x + (float(w) - dw) / 2.0
        dy = y + (float(h) - dh) / 2.0
        if frame:
            self.rect(x, y, w, h, fill=(0.96, 0.96, 0.97), stroke=RULE)
        self._ops().append("q %.3f 0 0 %.3f %.3f %.3f cm /%s Do Q"
                           % (dw, dh, dx, dy, entry["name"]))
        self._pages[-1]["images"].append(entry["name"])
        return self

    # -- serialisation ----------------------------------------------------
    def save(self, path):
        """Write the PDF. At least one page is required."""
        if not self._pages:
            raise PdfError("EMPTY_DOCUMENT", "nothing to save")
        objects = []

        def add(body):
            objects.append(body)
            return len(objects)          # object number (1-based)

        add(b"<< /Type /Catalog /Pages 2 0 R >>")   # 1
        pages_id = add(b"")                          # 2, filled in below
        for name in _FONT_ORDER:                     # 3, 4, 5
            add(("<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                 "/Encoding /WinAnsiEncoding >>" % name).encode("ascii"))

        # Pages first: a page object is always immediately followed by its
        # content stream, so content id == page id + 1.
        page_ids = []
        for page in self._pages:
            page_ids.append(len(objects) + 1)
            add(b"")                                  # page placeholder
            content = "\n".join(page["ops"]).encode("latin-1", "replace")
            add(b"<< /Length %d >>\nstream\n" % len(content)
                + content + b"\nendstream")

        used = []
        for page in self._pages:
            for name in page["images"]:
                if name not in used:
                    used.append(name)
        image_ids = {}
        for name in used:               # reserve ids; bodies fill in below
            image_ids[name] = add(b"")
        font_ids = {FONTS[f][0]: 3 + i for i, f in enumerate(_FONT_ORDER)}
        font_res = " ".join("/%s %d 0 R" % (FONTS[f][0], font_ids[FONTS[f][0]])
                            for f in _FONT_ORDER)
        for page, pid in zip(self._pages, page_ids):
            res = "<< /Font << %s >>" % font_res
            page_names = [n for n in used if n in page["images"]]
            if page_names:
                res += " /XObject << %s >>" % " ".join(
                    "/%s %d 0 R" % (n, image_ids[n]) for n in page_names)
            res += " /ProcSet [/PDF /Text /ImageB /ImageC] >>"
            objects[pid - 1] = (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] "
                "/Resources %s /Contents %d 0 R >>"
                % (self.width, self.height, res, pid + 1)).encode("utf-8")

        objects[pages_id - 1] = ("<< /Type /Pages /Count %d /Kids [%s] >>"
                                 % (len(page_ids),
                                    " ".join("%d 0 R" % i for i in page_ids))
                                 ).encode("utf-8")

        for name in used:
            e = self._by_name[name]
            objects[image_ids[name] - 1] = (
                b"<< /Type /XObject /Subtype /Image /Width %d /Height %d "
                b"/ColorSpace %s /BitsPerComponent 8 /Filter /%s /Length %d >>\n"
                b"stream\n" % (e["w"], e["h"], e["colorspace"].encode("ascii"),
                               e["filter"].encode("ascii"), len(e["data"]))
                + e["data"] + b"\nendstream")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for i, body in enumerate(objects, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i
            out += body
            out += b"\nendobj\n"
        xref_at = len(out)
        out += b"xref\n0 %d\n" % (len(objects) + 1)
        out += b"0000000000 65535 f \n"
        for off in offsets[1:]:
            out += b"%010d 00000 n \n" % off
        out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objects) + 1, xref_at))
        with open(path, "wb") as fh:
            fh.write(bytes(out))
        return path


_STREAM_RE = re.compile(
    rb"<<(?P<dict>[^>]*)>>\s*stream\r?\n(?P<data>.*?)\r?\nendstream", re.S)
_TEXT_RE = re.compile(rb"\((?:\\.|[^\\()])*\)")


def _unescape(body):
    out, i = bytearray(), 0
    while i < len(body):
        if body[i:i + 1] == b"\\" and i + 1 < len(body):
            nxt = body[i + 1:i + 2]
            out += b"(" if nxt == b"(" else b")" if nxt == b")" else nxt
            i += 2
        else:
            out += body[i:i + 1]
            i += 1
    return out.decode("cp1252", "replace")


def extract_text(pdf_bytes):
    """Plain text of every unfiltered (page content) stream -- for QC scans.

    Image streams carry a /Filter and are skipped, so binary never leaks in.
    """
    out = []
    for match in _STREAM_RE.finditer(pdf_bytes):
        head = match.group("dict")
        if b"/Filter" in head or b"/Length" not in head:
            continue
        data = match.group("data")
        if b"BT" not in data:
            continue
        for token in _TEXT_RE.findall(data):
            out.append(_unescape(token[1:-1]))
        out.append("\n")
    return " ".join(out)


__all__ = [
    "MIN_PT", "BODY_PT", "LEADING", "PAGE_W", "PAGE_H", "MARGIN",
    "PAPER", "INK", "MUTED", "RULE", "ACCENT",
    "PdfError", "Canvas", "text_width", "wrap", "block_height",
    "extract_text",
]
