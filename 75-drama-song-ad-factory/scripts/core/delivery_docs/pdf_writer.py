#!/usr/bin/env python3
"""pdf_writer: the standard-library page layout engine behind the client-facing
delivery PDFs (DEL-03 and its siblings).

Nothing here is paid, generated or measured: it draws text and rules onto US
Letter pages and packs them into a PDF. No third-party library, no font file,
no network -- the base-14 Helvetica faces are part of every PDF reader, so the
document needs no embedding and opens the same everywhere.

House style, shared with `references/CLIENT-GUIDE.md`: a bright white page,
deep-ink body copy, one warm accent for labels and section heads. Nothing is
set below MIN_PT -- the floor is enforced in code, not by convention, because
a client-facing page that has to be zoomed is not readable.

Run: python3 delivery_docs/test_pdf_writer.py
"""
from __future__ import annotations

# US Letter, in PostScript points.
PAGE_W, PAGE_H = 612.0, 792.0
MARGIN_L, MARGIN_R = 64.0, 64.0
MARGIN_T, MARGIN_B = 64.0, 80.0

# Client-facing floor: nothing renders below this, on any page.
MIN_PT = 12.0

# Palette (RGB, 0-1). Bright page, warm accent, ink that stays ink in print.
WHITE = (1.0, 1.0, 1.0)
INK = (0.10, 0.12, 0.16)
GREY = (0.38, 0.40, 0.45)
ACCENT = (0.64, 0.36, 0.04)
HAIR = (0.85, 0.86, 0.88)
BAR = (0.77, 0.47, 0.09)

# Font resource names -> base-14 face. F3 (oblique) reuses the roman widths.
FACES = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Helvetica-Oblique"}
_OBLIQUE_IS_ROMAN = "F3"

# Adobe core-14 advance widths, units of 1/1000 em, bytes 32..126.
_REGULAR = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)
_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
)
_WIDTHS = {"F1": _REGULAR, "F2": _BOLD, "F3": _REGULAR}

# WinAnsi positions outside 32..126. Values are the wider of roman/bold so a
# measurement can never under-estimate and push a line past the margin.
_WIDE = {0x96: 556, 0x97: 1000, 0x91: 278, 0x92: 278,
         0x93: 500, 0x94: 500, 0x95: 350, 0x85: 1000, 0xA0: 278}
_WIDE_DEFAULT = 780


def _byte(ch):
    """One WinAnsi byte for a character; anything unmappable becomes '?'."""
    try:
        return ch.encode("cp1252")[0]
    except UnicodeEncodeError:
        return ord("?")


def text_width(text, font, size):
    """Rendered width of `text` in points."""
    if font not in _WIDTHS:
        raise ValueError("unknown font %r" % (font,))
    table = _WIDTHS[font]
    units = 0
    for ch in text:
        b = _byte(ch)
        units += table[b - 32] if 32 <= b <= 126 else _WIDE.get(b, _WIDE_DEFAULT)
    return units * float(size) / 1000.0


def wrap(text, font, size, max_width):
    """Greedy word wrap. Never returns a line wider than `max_width`."""
    if max_width <= 0:
        raise ValueError("max_width must be positive")
    out = []
    for para in str(text).split("\n"):
        words = para.split()
        if not words:
            out.append("")
            continue
        cur = ""
        for word in words:
            cand = word if not cur else cur + " " + word
            if text_width(cand, font, size) <= max_width:
                cur = cand
                continue
            if cur:
                out.append(cur)
                cur = ""
            if text_width(word, font, size) <= max_width:
                cur = word
                continue
            piece = ""
            for ch in word:                      # one unbreakable word is too wide
                if text_width(piece + ch, font, size) <= max_width:
                    piece += ch
                else:
                    if piece:
                        out.append(piece)
                    piece = ch
            cur = piece
        if cur:
            out.append(cur)
    return out or [""]


def fit(text, font, size, max_width):
    """One line at most `max_width` wide, cut with an ellipsis when it is not."""
    text = str(text)
    if text_width(text, font, size) <= max_width:
        return text
    cut = text
    while cut and text_width(cut + "...", font, size) > max_width:
        cut = cut[:-1]
    return (cut.rstrip() + "...") if cut else "..."


def _esc(text):
    """PDF literal-string body: ASCII only, everything else an octal escape."""
    out = []
    for b in str(text).encode("cp1252", errors="replace"):
        if b in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(b))
        elif 32 <= b <= 126:
            out.append(chr(b))
        else:
            out.append("\\%03o" % b)
    return "".join(out)


def _num(value):
    return ("%.2f" % value).rstrip("0").rstrip(".") or "0"


def _text_op(x, y, text, font, size, color):
    r, g, b = color
    return "BT /%s %s Tf %s %s %s rg 1 0 0 1 %s %s Tm (%s) Tj ET" % (
        font, _num(size), _num(r), _num(g), _num(b),
        _num(x), _num(y), _esc(text))


def _rect_op(x, y, w, h, color):
    r, g, b = color
    return "%s %s %s rg %s %s %s %s re f" % (
        _num(r), _num(g), _num(b), _num(x), _num(y), _num(w), _num(h))


class Layout:
    """A flowing multi-page text document.

    `y` is the top of the free area and only ever moves down; `need()` starts a
    new page rather than drawing past the footer, so no block is ever clipped.
    """

    def __init__(self, *, left=MARGIN_L, right=MARGIN_R,
                 top=MARGIN_T, bottom=MARGIN_B):
        if min(left, right, top, bottom) < 0:
            raise ValueError("margins must be non-negative")
        self.left, self.right = float(left), float(right)
        self.top, self.bottom = float(top), float(bottom)
        self.pages = []
        self._footer = None
        self._new_page()

    # -- page frame --
    @property
    def content_w(self):
        return PAGE_W - self.left - self.right

    def _ops(self):
        return self.pages[-1]

    def _new_page(self):
        self.pages.append([_rect_op(0, PAGE_H - 8, PAGE_W, 8, BAR)])
        self.y = PAGE_H - self.top

    def on_footer(self, fn):
        """fn(page_number, total) -> list of ops, stamped by to_bytes()."""
        self._footer = fn

    def need(self, height):
        if self.y - float(height) < self.bottom:
            self._new_page()

    def space(self, height):
        height = float(height)
        self.need(height)
        self.y -= height

    def rule(self, height, color, width=None):
        """A filled bar `height` points tall across `width` (default full).

        A rule is not type, so MIN_PT does not apply to it -- only `para`
        carries the type floor.
        """
        if float(height) <= 0:
            raise ValueError("rule height must be positive")
        self.need(float(height))
        w = self.content_w if width is None else float(width)
        self.y -= float(height)
        self._ops().append(_rect_op(self.left, self.y, w, float(height), color))

    def para(self, text, *, font="F1", size=13.0, color=INK,
             indent=0.0, leading=None, space_before=0.0):
        """Draw one wrapped paragraph. Blank source lines become blank space."""
        if float(size) < MIN_PT:
            raise ValueError("type floor is %g pt, got %g" % (MIN_PT, size))
        lead = float(leading) if leading is not None else round(size * 1.45)
        if lead < size:
            raise ValueError("leading %g is tighter than the type (%g)" % (lead, size))
        if space_before:
            self.space(float(space_before))
        width = self.content_w - float(indent)
        for line in wrap(text, font, size, width):
            self.need(lead)
            if line:
                baseline = self.y - float(size) * 0.80
                self._ops().append(
                    _text_op(self.left + float(indent), baseline, line,
                             font, size, color))
            self.y -= lead
        return self

    # -- output --
    def to_bytes(self):
        total = len(self.pages)
        pages = []
        for index, ops in enumerate(self.pages):
            stamped = list(ops)
            if self._footer is not None:
                stamped.extend(self._footer(index + 1, total))
            pages.append(stamped)
        return _assemble(pages)


def _assemble(pages):
    """Serialise page content streams into a PDF 1.4 file."""
    objs = []

    def add(body):
        objs.append(body)
        return len(objs)                     # 1-based object number

    catalog = add(b"")                      # filled once the pages id is known
    page_tree = add(b"")
    fonts = {name: add(
        ("<< /Type /Font /Subtype /Type1 /BaseFont /%s "
         "/Encoding /WinAnsiEncoding >>" % base).encode("ascii"))
        for name, base in FACES.items()}
    font_res = " ".join("/%s %d 0 R" % (n, i) for n, i in sorted(fonts.items()))
    page_ids = []
    for ops in pages:
        pid = add(b"")
        stream = "\n".join(ops).encode("ascii", "replace")
        cid = add(b"<< /Length %d >>\nstream\n" % len(stream)
                  + stream + b"\nendstream")
        page_ids.append(pid)
        objs[pid - 1] = (
            ("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %s %s] "
             "/Resources << /ProcSet [/PDF /Text] /Font << %s >> >> "
             "/Contents %d 0 R >>"
             % (page_tree, _num(PAGE_W), _num(PAGE_H), font_res, cid))
            .encode("ascii"))
    objs[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % page_tree
    objs[page_tree - 1] = (
        b"<< /Type /Pages /Count %d /Kids [%s] >>"
        % (len(page_ids),
           " ".join("%d 0 R" % i for i in page_ids).encode("ascii")))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number
        out += body
        out += b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, catalog, xref))
    return bytes(out)
