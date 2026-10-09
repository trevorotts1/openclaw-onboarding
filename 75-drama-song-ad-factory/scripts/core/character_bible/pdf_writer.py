#!/usr/bin/env python3
"""pdf_writer: a small, dependency-free PDF writer for the skill's client PDFs.

Standard library only -- no reportlab, no weasyprint, no renderer binary. The
skill's tests run under an empty HOME with only numpy installed, so a client
PDF cannot depend on a package that is not there. Content streams are written
UNCOMPRESSED on purpose: the font-floor gate and the text checks read the
output file itself, never the author's intent.

Layout contract shared by every client-facing PDF this skill ships:

  * Letter page, generous margins, white page, dark ink -- bright and readable;
  * NOTHING is drawn below ``MIN_FONT_PT`` (12 point). ``text()`` refuses a
    smaller size instead of drawing it, and ``check_font_floor()`` re-reads the
    finished file and fails on any ``Tf`` under the floor, so a regression in
    either place still gets caught (template-side gate, output-side gate);
  * base-14 Helvetica only -- no font embedding, no renderer-specific behaviour.

ponytail: widths come from the Helvetica AFM table for ASCII, accents resolve
to their base letter, anything else falls back to 556 and is drawn as ``?``.
Add a full WinAnsi table only if a client name genuinely needs one.
"""
from __future__ import annotations

import re
import struct
import unicodedata
import zlib

MIN_FONT_PT = 12.0
PAGE_W, PAGE_H = 612.0, 792.0
MARGIN = 54.0

FONTS = {"regular": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique"}
HAIRLINE_LINE = (0.84, 0.86, 0.88)

#: Helvetica AFM widths (1/1000 em) for ASCII 32..126.
_HELV_ASCII = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
assert len(_HELV_ASCII) == 95, len(_HELV_ASCII)

#: Typographic characters clients paste in, folded to ASCII before encoding.
_TRANSLIT = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
    "•": "-", "­": "", "″": '"', "′": "'",
}

#: Bold is drawn wider than regular; wrap bold a little tighter than the table says.
_BOLD_SLACK = 0.94
_REGULAR_SLACK = 0.97
_FALLBACK_WIDTH = 556

_TF_RE = re.compile(rb"([0-9]+(?:\.[0-9]+)?)\s+Tf\b")
_DEACCENT = {"́": "", "̀": "", "̈": "", "̧": "", "̃": "", "̣": ""}


class PdfError(Exception):
    """A refusal this writer owns. ``code`` is what tests print."""


def _base_char(ch):
    for combining, _gap in _DEACCENT.items():
        ch = ch.replace(combining, "")
    return ch


def char_width(ch, size, font="regular"):
    """Advance width of one character in points."""
    if ch in _TRANSLIT:
        ch = _TRANSLIT[ch]
    if len(ch) != 1:
        return _FALLBACK_WIDTH / 1000.0 * size
    ch = _base_char(ch)
    code = ord(ch)
    if 32 <= code <= 126:
        w = _HELV_ASCII[code - 32]
    elif 160 <= code <= 255:
        base = unicodedata.normalize("NFD", ch)[0]
        w = char_width(base, 1000.0, font)
        return w / 1000.0 * size
    else:
        w = _FALLBACK_WIDTH
    if font == "bold":
        w *= 1.06
    return w / 1000.0 * size


def text_width(s, size, font="regular"):
    return sum(char_width(c, size, font) for c in s)


def encode_text(s):
    """WinAnsi bytes for a run of text; unmappable characters become ``?``."""
    out = []
    for ch in s:
        if ch in "\r\n\t":
            ch = " "
        if ch in _TRANSLIT:
            ch = _TRANSLIT[ch]
        try:
            b = ch.encode("latin-1")
        except UnicodeEncodeError:
            b = b"?"
        if len(b) == 1 and 128 <= b[0] <= 159:
            b = b"?"
        out.append(b)
    return b"".join(out)


def _escape(raw):
    out = bytearray()
    for b in raw:
        if b in (0x28, 0x29, 0x5C):      # ( ) \
            out += b"\\" + bytes([b])
        elif b < 32 or b > 126:
            out += b"\\%03o" % b
        else:
            out.append(b)
    return bytes(out)


def _color(rgb):
    return " ".join("%.3f" % c for c in rgb)


def wrap(s, size, width, font="regular"):
    """Greedy word wrap at ``width`` points; a single long word is hard-broken."""
    slack = _BOLD_SLACK if font == "bold" else _REGULAR_SLACK
    limit = width * slack
    lines, cur = [], ""
    for word in str(s).split():
        trial = word if not cur else cur + " " + word
        if text_width(trial, size, font) <= limit:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        if text_width(word, size, font) <= limit:
            cur = word
            continue
        piece = ""
        for ch in word:
            if piece and text_width(piece + ch, size, font) > limit:
                lines.append(piece)
                piece = ch
            else:
                piece += ch
        cur = piece
    if cur:
        lines.append(cur)
    return lines or [""]


def _read_png(data):
    """Decode a non-interlaced 8-bit PNG into (width, height, RGB bytes)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise PdfError("NOT_A_PNG: reference image is not a PNG")
    pos, chunks = 8, {}
    idat = []
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            chunks["IHDR"] = body
        elif kind == b"PLTE":
            chunks["PLTE"] = body
        elif kind == b"tRNS":
            chunks["tRNS"] = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if "IHDR" not in chunks or not idat:
        raise PdfError("PNG_INCOMPLETE: reference image is missing PNG header data")
    w, h, depth, ctype, _comp, filt, interlace = struct.unpack(">IIBBBBB", chunks["IHDR"])
    if depth != 8 or interlace != 0 or ctype not in (0, 2, 3, 6):
        raise PdfError("PNG_UNSUPPORTED: reference image must be a non-interlaced "
                       "8-bit grayscale, palette, RGB or RGBA PNG")
    channels = {0: 1, 2: 3, 3: 1, 6: 4}[ctype]
    raw = zlib.decompress(b"".join(idat))
    stride = w * channels
    rows, prev, at = [], bytearray(stride), 0
    for _y in range(h):
        f = raw[at]
        at += 1
        line = bytearray(raw[at:at + stride])
        at += stride
        if len(line) != stride:
            raise PdfError("PNG_TRUNCATED: reference image pixel data is short")
        if f == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        elif f != 0:
            raise PdfError("PNG_FILTER: reference image uses an unknown row filter")
        prev = bytearray(line)
        rows.append(line)
    pal, trns = chunks.get("PLTE", b""), chunks.get("tRNS", b"")
    out = bytearray()
    for line in rows:
        if ctype == 0:
            for g in line:
                out += bytes((g, g, g))
        elif ctype == 2:
            out += line
        elif ctype == 3:
            for idx in line:
                if idx * 3 + 3 > len(pal):
                    raise PdfError("PNG_PALETTE: reference image palette is short")
                r, g, b = pal[idx * 3:idx * 3 + 3]
                out += bytes((r, g, b))
        else:
            for i in range(0, len(line), 4):
                r, g, b, a = line[i:i + 4]
                if a != 255:                      # composite over white: bright, never murky
                    r = (r * a + 255 * (255 - a)) // 255
                    g = (g * a + 255 * (255 - a)) // 255
                    b = (b * a + 255 * (255 - a)) // 255
                out += bytes((r, g, b))
    if trns and ctype == 3:                        # palette transparency -> white
        rebuilt = bytearray()
        for line in rows:
            for idx in line:
                a = trns[idx] if idx < len(trns) else 255
                r, g, b = pal[idx * 3:idx * 3 + 3]
                if a != 255:
                    r = (r * a + 255 * (255 - a)) // 255
                    g = (g * a + 255 * (255 - a)) // 255
                    b = (b * a + 255 * (255 - a)) // 255
                rebuilt += bytes((r, g, b))
        out = rebuilt
    return w, h, bytes(out)


def _read_jpeg(data):
    """Probe a JPEG for size and component count; bytes are embedded verbatim."""
    if data[:2] != b"\xff\xd8":
        raise PdfError("NOT_A_JPEG: reference image is not a JPEG")
    pos, comps = 2, 3
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        seglen = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[pos + 5:pos + 9])
            comps = data[pos + 9]
            return w, h, comps, data
        pos += 2 + seglen
    raise PdfError("JPEG_INCOMPLETE: reference image has no size marker")


class Doc:
    """One Letter-size document. Create pages, draw, then ``save()``."""

    def __init__(self, page_w=PAGE_W, page_h=PAGE_H):
        self.page_w, self.page_h = float(page_w), float(page_h)
        self._pages = []
        self._images = []          # (name, payload dict)
        self._image_keys = {}
        self.page()

    # -- pages ------------------------------------------------------------
    def page(self):
        self._current = {"ops": [], "images": []}
        self._pages.append(self._current)
        return self._current

    @property
    def page_count(self):
        return len(self._pages)

    def _op(self, s):
        self._current["ops"].append(s)

    # -- drawing ----------------------------------------------------------
    def fill_rect(self, x, y, w, h, rgb):
        self._op("%s rg %.2f %.2f %.2f %.2f re f" % (_color(rgb), x, y, w, h))

    def stroke_rect(self, x, y, w, h, rgb, width=1.0, dashed=False):
        self._op("%.2f w %s RG" % (width, _color(rgb)))
        if dashed:
            self._op("[4 3] 0 d")
        self._op("%.2f %.2f %.2f %.2f re S" % (x, y, w, h))
        if dashed:
            self._op("[] 0 d")

    def line(self, x1, y1, x2, y2, rgb, width=1.0):
        self._op("%.2f w %s RG %.2f %.2f m %.2f %.2f l S"
                 % (width, _color(rgb), x1, y1, x2, y2))

    def text(self, x, y, s, size=12.0, font="regular", rgb=(0.10, 0.10, 0.10)):
        """Draw one line with its baseline at ``y``. Refuses anything under the floor."""
        size = float(size)
        if size < MIN_FONT_PT:
            raise PdfError("FONT_FLOOR: %.1f pt is under the %.0f pt client floor"
                           % (size, MIN_FONT_PT))
        if font not in FONTS:
            raise PdfError("UNKNOWN_FONT: %r" % (font,))
        self._op("BT %s rg /%s %.1f Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET"
                 % (_color(rgb), _font_res(font), size, x, y,
                    _escape(encode_text(str(s))).decode("latin-1")))

    def paragraph(self, x, y, s, size, width, leading=None, font="regular",
                  rgb=(0.10, 0.10, 0.10)):
        """Draw wrapped text with the FIRST baseline at ``y``; return the next free y."""
        leading = leading or size * 1.38
        for i, ln in enumerate(wrap(s, size, width, font)):
            self.text(x, y - i * leading, ln, size, font, rgb)
        n = len(wrap(s, size, width, font))
        return y - (n - 1) * leading - leading

    def image(self, path, x, y, w, h):
        """Draw an image letterboxed inside the box, never cropped."""
        payload = self._load_image(path)
        iw, ih = payload["width"], payload["height"]
        if not iw or not ih:
            raise PdfError("IMAGE_EMPTY: reference image has no pixels")
        scale = min(w / float(iw), h / float(ih))
        dw, dh = iw * scale, ih * scale
        dx, dy = x + (w - dw) / 2.0, y + (h - dh) / 2.0
        name = payload["name"]
        if name not in self._current["images"]:
            self._current["images"].append(name)
        self._op("q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q" % (dw, dh, dx, dy, name))

    def placeholder(self, x, y, w, h, lines):
        """A framed, clearly-labelled box for a view the client has not sent."""
        self.fill_rect(x, y, w, h, (0.965, 0.972, 0.976))
        self.stroke_rect(x, y, w, h, (0.78, 0.81, 0.83), 1.0, dashed=True)
        mid = y + h / 2.0 + (len(lines) - 1) * 8
        for i, ln in enumerate(lines):
            tw = text_width(ln, 12.0, "regular")
            self.text(x + (w - tw) / 2.0, mid - i * 16, ln, 12.0, "regular",
                      (0.32, 0.36, 0.39))

    def _load_image(self, path):
        key = str(path)
        if key in self._image_keys:
            return self._image_keys[key]
        with open(path, "rb") as fh:
            data = fh.read()
        idx = len(self._images) + 1
        name = "Im%d" % idx
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h, rgb = _read_png(data)
            payload = {"name": name, "width": w, "height": h, "filter": "/FlateDecode",
                       "colorspace": "/DeviceRGB", "bits": 8, "data": zlib.compress(rgb, 9)}
        else:
            w, h, comps, blob = _read_jpeg(data)
            payload = {"name": name, "width": w, "height": h, "filter": "/DCTDecode",
                       "colorspace": "/DeviceGray" if comps == 1 else "/DeviceRGB",
                       "bits": 8, "data": blob}
        self._images.append(payload)
        self._image_keys[key] = payload
        return payload

    def draw_footers(self, left_text):
        """Stamp the same footer on every page already built (page count is known)."""
        total = len(self._pages)
        keep = self._current
        for i, pg in enumerate(self._pages, 1):
            self._current = pg
            self.line(MARGIN, 88.0, self.page_w - MARGIN, 88.0, HAIRLINE_LINE, 0.75)
            self.text(MARGIN, 70.0, left_text, 12, "regular", (0.36, 0.40, 0.42))
            label = "Page %d of %d" % (i, total)
            self.text(self.page_w - MARGIN - text_width(label, 12), 70.0,
                      label, 12, "regular", (0.36, 0.40, 0.42))
        self._current = keep

    # -- output -----------------------------------------------------------
    def save(self, path):
        objs = []                                    # 1-based object bodies

        def add(body):
            objs.append(body)
            return len(objs)

        catalog_id = add(None)
        pages_id = add(None)
        regular_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                         "/Encoding /WinAnsiEncoding >>")
        bold_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                      "/Encoding /WinAnsiEncoding >>")
        italic_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique "
                        "/Encoding /WinAnsiEncoding >>")
        img_ids = {}
        for payload in self._images:
            img_ids[payload["name"]] = add(
                "<< /Type /XObject /Subtype /Image /Width %d /Height %d "
                "/ColorSpace %s /BitsPerComponent %d /Filter %s /Length %d >>\nstream\n"
                "%s\nendstream"
                % (payload["width"], payload["height"], payload["colorspace"],
                   payload["bits"], payload["filter"], len(payload["data"]),
                   payload["data"].decode("latin-1")))

        page_ids = []
        for pg in self._pages:
            content = ("\n".join(pg["ops"]) + "\n").encode("latin-1")
            content_id = add("<< /Length %d >>\nstream\n%s\nendstream"
                             % (len(content), content.decode("latin-1")))
            xobjects = "".join("/%s %d 0 R " % (n, img_ids[n]) for n in pg["images"])
            page_ids.append(add(
                "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.0f %.0f] "
                "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >>%s>> "
                "/Contents %d 0 R >>"
                % (pages_id, self.page_w, self.page_h, regular_id, bold_id, italic_id,
                   ("/XObject << %s>>" % xobjects) if xobjects else "", content_id)))

        objs[catalog_id - 1] = "<< /Type /Catalog /Pages %d 0 R >>" % pages_id
        objs[pages_id - 1] = ("<< /Type /Pages /Count %d /Kids [%s] >>"
                              % (len(page_ids), " ".join("%d 0 R" % i for i in page_ids)))

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += ("%d 0 obj\n%s\nendobj\n" % (i, body)).encode("latin-1")
        xref_at = len(out)
        out += ("xref\n0 %d\n" % (len(objs) + 1)).encode("ascii")
        out += b"0000000000 65535 f \n"
        for off in offsets[1:]:
            out += ("%010d 00000 n \n" % off).encode("ascii")
        out += ("trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objs) + 1, catalog_id, xref_at)).encode("ascii")
        with open(path, "wb") as fh:
            fh.write(bytes(out))
        return path


def _font_res(font):
    return {"regular": "F1", "bold": "F2", "italic": "F3"}[font]


def font_sizes(path):
    """Every font size (point) the file's content streams actually use.

    Only UNFILTERED streams are read: those are the page content streams, so
    compressed image bytes can never be mistaken for a ``Tf`` operator.
    """
    with open(path, "rb") as fh:
        blob = fh.read()
    sizes = set()
    for m in re.finditer(rb"stream\r?\n", blob):
        head = blob[max(0, m.start() - 512):m.start()]
        if b"/Filter" in head[head.rfind(b"<<"):]:   # image/object stream: skip
            continue
        end = blob.find(b"endstream", m.end())
        if end < 0:
            continue
        chunk = blob[m.end():end].rstrip(b"\r\n")
        for hit in _TF_RE.finditer(chunk):
            sizes.add(float(hit.group(1)))
        if not _TF_RE.search(chunk):
            try:
                dec = zlib.decompress(chunk)
            except Exception:                       # not a Flate stream; skip
                continue
            for hit in _TF_RE.finditer(dec):
                sizes.add(float(hit.group(1)))
    return sorted(sizes)


def check_font_floor(path, minimum=MIN_FONT_PT):
    """Raise when the FINISHED file draws anything under the floor."""
    sizes = font_sizes(path)
    if not sizes:
        raise PdfError("NO_TEXT: %s carries no text to measure" % path)
    bad = [s for s in sizes if s < float(minimum)]
    if bad:
        raise PdfError("FONT_FLOOR: %s draws %s pt, under the %.0f pt floor"
                       % (path, ", ".join("%.1f" % s for s in bad), minimum))
    return sizes
