"""DEL-12: the one-page client WELCOME SHEET (PDF) for the delivery folder.

Bright, readable, one page, nothing under 12 pt, matching the approved
client-guide look: a friendly title, a gold rule, then every file in the
folder with its number and one sentence on what it is for. The sheet is
rendered from ``package_items.PACKAGE_ITEMS`` only, so the page and the
delivery gate can never drift apart.

PDF writing is ~120 lines of stdlib: PDF 1.4, one page, base-14 Helvetica
(no embedding, no font file, no third-party library, no network, no spend).
Output is deterministic -- no creation date, no random id -- so two runs on
two machines produce identical bytes.

Run: python3 scripts/core/delivery_package/test_welcome_sheet_del12.py
"""
from __future__ import annotations

from pathlib import Path

from .package_items import (  # noqa: F401  (re-exported for callers)
    MIN_PDF_POINT_SIZE,
    PACKAGE_FILES,
    PACKAGE_ITEM_COUNT,
    PACKAGE_ITEMS,
    WELCOME_SHEET_FILE,
)

PAGE_W, PAGE_H = 612.0, 792.0          # US Letter, points
MARGIN = 46.0
CONTENT_W = PAGE_W - 2 * MARGIN         # 520
BADGE_W, BADGE_H = 26.0, 16.0
TEXT_X = MARGIN + BADGE_W + 6.0         # filenames / descriptions start here
TEXT_W = CONTENT_W - (TEXT_X - MARGIN)  # 488
LEADING = 15.0                          # one 13 pt line, airy
ROW_GAP = 7.0
DESC_GAP = 2.0

TITLE_SIZE = 21.0
#: Body type. 13 pt clears the 12 pt floor with room to read.
BODY_SIZE = 13.0
assert BODY_SIZE >= MIN_PDF_POINT_SIZE

NAVY = (0.09, 0.16, 0.31)
GOLD = (0.83, 0.62, 0.13)
INK = (0.16, 0.18, 0.22)
MUTED = (0.34, 0.36, 0.41)
WHITE = (1.0, 1.0, 1.0)

TITLE = "Welcome to Your Delivery Folder"
INTRO = ("Every file in this folder carries a number, so you always know "
         "what you are opening. This one page is your map: the number on "
         "the file matches the number below.")
FOOTER = ("All twelve items belong to this delivery - nothing is hidden and "
          "nothing is extra. If a file is missing, ask for that number first.")

#: Helvetica AFM widths, 1/1000 em, ASCII 32..126 (base-14, no embedding).
_REG_W = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
}
_BOLD_W = {
    " ": 278, "!": 333, '"': 474, "#": 556, "$": 556, "%": 889, "&": 722,
    "'": 238, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 333, ";": 333, "<": 584, "=": 584, ">": 584,
    "?": 611, "@": 975, "[": 333, "\\": 278, "]": 333, "^": 584, "_": 556,
    "`": 333, "{": 389, "|": 280, "}": 389, "~": 584,
    "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333, "g": 611,
    "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889, "n": 611,
    "o": 611, "p": 611, "q": 611, "r": 389, "s": 556, "t": 333, "u": 611,
    "v": 556, "w": 778, "x": 556, "y": 556, "z": 500,
}
for _d in "0123456789":
    _REG_W[_d] = 556
    _BOLD_W[_d] = 556


class WelcomeSheetError(Exception):
    """The sheet did not fit, or the package contract was broken."""


def text_width(s, size, bold=False):
    """Rendered width of ``s`` in points (Helvetica AFM widths)."""
    table = _BOLD_W if bold else _REG_W
    return sum(table.get(ch, 556) for ch in s) * size / 1000.0


def wrap(s, max_width, size, bold=False):
    """Greedy word wrap. Long unbreakable words are split hard."""
    words, lines, cur = s.split(), [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(trial, size, bold) <= max_width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        while text_width(cur, size, bold) > max_width and len(cur) > 1:
            cut = len(cur)
            while cut > 1 and text_width(cur[:cut], size, bold) > max_width:
                cut -= 1
            lines.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        lines.append(cur)
    return lines or [""]


def _esc(s):
    out = []
    for ch in s:
        if ch in "()\\":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _rgb(color):
    return "%.3f %.3f %.3f rg" % color


def _text_op(x, y, s, size, bold=False, color=INK):
    font = "/F2" if bold else "/F1"
    return ("%s\nBT %s %.1f Tf %.2f %.2f Td (%s) Tj ET"
            % (_rgb(color), font, size, x, y, _esc(s)))


def _rect_op(x, y, w, h, color):
    return "%s\n%.2f %.2f %.2f %.2f re f" % (_rgb(color), x, y, w, h)


def _row_lines(item):
    """(kind, text) lines for one package item, in drawing order."""
    lines = [("file", name) for name in item["files"]]
    for para in wrap(item["what"], TEXT_W, BODY_SIZE):
        lines.append(("desc", para))
    return lines


def render_lines():
    """Everything the sheet draws, as ops plus the final cursor.

    Raises WelcomeSheetError when the page would overflow -- a loud failure
    instead of a second page or clipped text.
    """
    ops = []
    top = PAGE_H - MARGIN
    cy = top

    # Title + gold rule (client-guide look: friendly heading, one gold line)
    cy -= TITLE_SIZE * 0.85
    ops.append(_text_op(MARGIN, cy, TITLE, TITLE_SIZE, bold=True, color=NAVY))
    cy -= 10.0
    ops.append(_rect_op(MARGIN, cy - 3.0, CONTENT_W, 3.0, GOLD))
    cy -= 14.0

    for line in wrap(INTRO, CONTENT_W, BODY_SIZE):
        cy -= LEADING
        ops.append(_text_op(MARGIN, cy, line, BODY_SIZE, color=INK))
    cy -= 8.0

    for item in PACKAGE_ITEMS:
        rows = _row_lines(item)
        baseline = cy - LEADING * 0.85
        # number badge -- the number the file name carries
        ops.append(_rect_op(MARGIN, baseline - 3.5, BADGE_W, BADGE_H, NAVY))
        digits = "%02d" % item["number"]
        num_w = text_width(digits, BODY_SIZE, bold=True)
        ops.append(_text_op(MARGIN + (BADGE_W - num_w) / 2.0, baseline,
                            digits, BODY_SIZE, bold=True, color=WHITE))
        for idx, (kind, line) in enumerate(rows):
            y = baseline - LEADING * idx
            if kind == "file":
                ops.append(_text_op(TEXT_X, y, line, BODY_SIZE, bold=True,
                                    color=NAVY))
            else:
                ops.append(_text_op(TEXT_X, y, line, BODY_SIZE, color=INK))
        cy = baseline - LEADING * (len(rows) - 1) - DESC_GAP - ROW_GAP

    cy -= 6.0
    ops.append(_rect_op(MARGIN, cy - 3.0, CONTENT_W, 1.5, GOLD))
    for line in wrap(FOOTER, CONTENT_W, BODY_SIZE):
        cy -= LEADING
        ops.append(_text_op(MARGIN, cy, line, BODY_SIZE, color=MUTED))

    if cy - 6.0 < MARGIN:
        raise WelcomeSheetError(
            "welcome sheet overflow: content ends at %.1f pt, page floor is "
            "%.1f pt" % (cy - 6.0, MARGIN))
    return ops


def pdf_bytes():
    """Deterministic single-page PDF of the welcome sheet."""
    content = "\n".join(render_lines()).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
         b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> "
         b"/Contents 6 0 R >>"),
        (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
         b"/Encoding /WinAnsiEncoding >>"),
        (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
         b"/Encoding /WinAnsiEncoding >>"),
        (b"<< /Length %d >>\nstream\n" % len(content)) + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    startxref = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, startxref))
    return bytes(out)


def build_welcome_sheet(path=None):
    """Write the sheet. Default name is item 12's canonical name."""
    target = Path(path) if path else Path(WELCOME_SHEET_FILE)
    data = pdf_bytes()
    if not data.startswith(b"%PDF-"):
        raise WelcomeSheetError("refusing to write a non-PDF")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": str(target), "bytes": len(data), "pages": 1,
            "items": PACKAGE_ITEM_COUNT, "files": len(PACKAGE_FILES)}


def _cli(argv=None):
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    out = args[0] if args else WELCOME_SHEET_FILE
    try:
        info = build_welcome_sheet(out)
    except WelcomeSheetError as exc:
        print("welcome-sheet: %s" % exc)
        return 5
    print("welcome-sheet: wrote %s (%d bytes, %d items, %d files)"
          % (info["path"], info["bytes"], info["items"], info["files"]))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
