#!/usr/bin/env python3
"""storyboard_grid.py: DEL-04 -- the storyboard delivered as one grid PDF.

The client approved every shot as a picture plus a written card
(``storyboard_director.approval_package``, the STORYBOARD APPROVAL gate). This
module hands that approval back as a document they can keep: a page grid of the
scene images, each captioned with the lyric line it plays over and what
happens, in song order, so nothing about the video is a surprise.

Reuse, never re-implemented here:
  * ``storyboard_director.approval_package.build`` -- the approved shot cards
    and the stills, already checked complete and fail-closed (a missing still
    or an incomplete card refuses here too, with that module's own code);
  * the run's storyboard approval records -- ``storyboard/gate.json`` (the
    approval that opened the 14.1 video gate), ``contracts.json``,
    ``stills.json``, ``shot-list.json``;
  * ``pdf_kit`` -- the shared delivery-PDF writer (12 pt floor, bright page).

Client-facing rules enforced before a byte is written (``forbidden_text``):
no model or tool name, no dollar amount, no income promise anywhere in the
document.

One delivery folder per client run, clear numbered file name:
``<delivery folder>/04 - Storyboard.pdf`` (``DELIVERY_NAME``).

Standard library only, no network, no spend, no absolute operator path.
Run: python3 scripts/core/storyboard_grid/test_storyboard_grid.py
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_HERE)                  # .../core
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import pdf_kit.pdf_kit as PDF                    # noqa: E402
import storyboard_director.approval_package as AP  # noqa: E402

TOOL_NAME = "storyboard_grid"
TOOL_VERSION = "1.0.0"

#: Numbered deliverable name inside the run's delivery folder. The name is the
#: ONE naming scheme, taken verbatim from the DEL-13 contract (``NN -
#: Label.ext``) -- never reformatted here, so the two cannot drift.
from delivery_package.contract import ITEMS_BY_KEY as _ITEMS  # noqa: E402

DELIVERY_NAME = _ITEMS["storyboard_pdf"].files[0]

DOC_TITLE_FALLBACK = "Your Video Storyboard"
SUBTITLE = "Every scene in order, with the line it plays over and what happens."

COLS = 2
GAP = 20.0
ROW_GAP = 22.0
LINE = 15.0                       # leading for caption text (12 pt * 1.25)

#: Whole-word bans: a model or tool name must never reach a client page.
#: ``cookie`` is not ``kie`` -- word boundaries do the work, not substring cut.
#: Only unambiguous names live here. Ordinary English that happens to be a
#: product name ("did", "runway", "llama" in a scene) is qualified instead, so
#: a real storyboard line can never be blocked by the guard itself.
FORBIDDEN_WORDS = (
    "claude", "anthropic", "openai", "chatgpt", "gpt", "gemini", "mistral",
    "deepseek", "qwen", "kimi", "ollama", "openrouter", "suno", "kie",
    "kling", "minimax", "pika", "elevenlabs", "heygen", "runwayml",
    "reportlab", "fpdf", "weasyprint", "pdftotext",
)
#: Income promises and dollar amounts stay out of every client-facing page.
FORBIDDEN_PHRASES = (
    "guaranteed income", "passive income", "make money", "earn money",
    "money back", "return on investment", "roi of", "profit", "revenue will",
    "runway ml", "runway gen", "llama 2", "llama 3", "llama 4", "d-id",
)
_DOLLAR = re.compile(r"[$]\s*\d|\d+\s*(?:dollars?|usd)\b", re.I)
_WORD_BANS = re.compile(r"\b(%s)\b" % "|".join(
    re.escape(w) for w in FORBIDDEN_WORDS), re.I)
_PHRASE_BANS = re.compile(r"(%s)" % "|".join(
    re.escape(p) for p in FORBIDDEN_PHRASES), re.I)


class GridError(Exception):
    """Named, fail-closed refusal."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def forbidden_text(text):
    """Every client-facing rule the string breaks (empty list = clean)."""
    hits = []
    body = str(text or "")
    for match in _WORD_BANS.finditer(body):
        hits.append("TOOL_OR_MODEL_NAME:%s" % match.group(0))
    for match in _PHRASE_BANS.finditer(body):
        hits.append("INCOME_PROMISE:%s" % match.group(0))
    for match in _DOLLAR.finditer(body):
        hits.append("DOLLAR_AMOUNT:%s" % match.group(0).strip())
    return hits


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _title(run_dir):
    """Client-facing heading: the approved script's title, else a generic one."""
    for rel in (os.path.join("creative", "script.json"),
                os.path.join("creative", "story.json")):
        doc = _read(os.path.join(run_dir, rel), {}) or {}
        t = str(doc.get("title") or "").strip()
        if t:
            return t
    return DOC_TITLE_FALLBACK


def load(run_dir):
    """The approved storyboard of ``run_dir`` as one buildable package.

    Returns ``{"title", "shots", "contracts", "stills", "items", "review",
    "approved_at"}``. Refuses (GridError) when the approval record is absent
    or when the approved cards/stills are not complete -- the approval gate's
    own codes are passed straight through.
    """
    run_dir = os.path.abspath(run_dir)
    sb = os.path.join(run_dir, "storyboard")
    gate = _read(os.path.join(sb, "gate.json"))
    if not isinstance(gate, dict) or not gate.get("shots"):
        raise GridError("STORYBOARD_NOT_APPROVED",
                        "storyboard/gate.json holds no approval record; the "
                        "storyboard PDF is built from what the client approved")
    shots = gate["shots"]
    contracts = _read(os.path.join(sb, "contracts.json"), {}) or {}
    raw_stills = _read(os.path.join(sb, "stills.json"), {}) or {}
    stills = {k: (v if os.path.isabs(v) else os.path.join(run_dir, v))
              for k, v in raw_stills.items()}
    pkg = AP.build(shots, contracts, stills)     # ordered, complete, fail-closed
    state = _read(os.path.join(sb, "approval.json"), {}) or {}
    return {"title": _title(run_dir), "shots": shots, "contracts": contracts,
            "stills": stills, "items": pkg["items"],
            "review": gate.get("review"), "approved_at": state.get("at")}


def _sentence(text):
    """Trim, drop a trailing full stop and capitalise the first letter."""
    body = (text or "").strip().rstrip(".")
    return body[:1].upper() + body[1:] if body else ""


def captions(items):
    """The caption block per shot: heading, lyric line, what happens, face."""
    rows = []
    for item in items:
        lyric = '"%s"' % item["line"]
        place, sep, action = item["where_action"].partition(" - ")
        if sep:
            where = "%s: %s" % (_sentence(place), _sentence(action))
        else:
            where = _sentence(item["where_action"])
        what = "What happens: %s. %s." % (where, _sentence(item["meaning"]))
        rows.append({
            "n": item["n"],
            "still": item["still"],
            "heading": "SHOT %d   %s" % (item["n"], item["time"]),
            "lyric": lyric,
            "what": what,
            "face": "Face: %s" % item["face_emotion"] if item["face_emotion"] else "",
        })
    return rows


def _document_text(title, rows):
    parts = [title, SUBTITLE]
    for row in rows:
        parts.extend([row["heading"], row["lyric"], row["what"], row["face"]])
    return "\n".join(p for p in parts if p)


def _cell_height(row, width):
    """Height _draw_cell will actually consume, gaps included.

    The gaps are not optional decoration: without them the measured cell is
    9 pt short and two rows can collide on a full page.
    """
    h = width * 9.0 / 16.0 + 8.0
    for key, font in (("heading", "Helvetica-Bold"),
                      ("lyric", "Helvetica-Oblique"),
                      ("what", "Helvetica"),
                      ("face", "Helvetica")):
        text = row.get(key)
        if text:
            h += PDF.block_height(text, width, font, PDF.BODY_PT, LINE)
    h += 6.0                       # after the heading, after the lyric
    h += 6.0
    if row.get("face"):
        h += 3.0                    # the third gap, only drawn with a face
    return h


def _draw_cell(canvas, x, y_top, width, row):
    img_h = width * 9.0 / 16.0
    canvas.image(row["still"], x, y_top - img_h, width, img_h)
    y = y_top - img_h - 8.0
    y = canvas.text_block(x, y, row["heading"], width,
                          font="Helvetica-Bold", size=PDF.BODY_PT,
                          leading=LINE, color=PDF.INK)
    y -= 3.0
    y = canvas.text_block(x, y, row["lyric"], width,
                          font="Helvetica-Oblique", size=PDF.BODY_PT,
                          leading=LINE, color=PDF.INK)
    y -= 3.0
    y = canvas.text_block(x, y, row["what"], width,
                          font="Helvetica", size=PDF.BODY_PT,
                          leading=LINE, color=PDF.INK)
    if row["face"]:
        y -= 3.0
        canvas.text_block(x, y, row["face"], width,
                          font="Helvetica", size=PDF.BODY_PT,
                          leading=LINE, color=PDF.MUTED)


def write_pdf(rows, out_path, title=DOC_TITLE_FALLBACK):
    """Render the grid. Refuses before drawing if any caption breaks a rule."""
    if not rows:
        raise GridError("STORYBOARD_EMPTY", "no shots to put in the storyboard")
    hits = forbidden_text(_document_text(title, rows))
    if hits:
        raise GridError("CLIENT_TEXT_FORBIDDEN",
                        "client-facing text carries a banned token: %s"
                        % ", ".join(sorted(set(hits))))

    width = (PDF.PAGE_W - 2 * PDF.MARGIN - (COLS - 1) * GAP) / COLS
    canvas = PDF.Canvas(margin=PDF.MARGIN)
    canvas.new_page()
    _footer(canvas, 1)
    y = PDF.PAGE_H - PDF.MARGIN
    y = _page_head(canvas, y, title, first=True)

    index = 0
    while index < len(rows):
        row_cells = rows[index:index + COLS]
        heights = [_cell_height(r, width) for r in row_cells]
        row_h = max(heights)
        if y - row_h < PDF.MARGIN + 24.0:
            canvas.new_page()
            _footer(canvas, canvas.pages)
            y = PDF.PAGE_H - PDF.MARGIN
            y = _page_head(canvas, y, title, first=False)
        for col, (row, _h) in enumerate(zip(row_cells, heights)):
            x = PDF.MARGIN + col * (width + GAP)
            _draw_cell(canvas, x, y, width, row)
        y -= row_h + ROW_GAP
        index += len(row_cells)
    return canvas.save(out_path)


def _page_head(canvas, y_top, title, first):
    # Both branches take the y the block actually ends at: a long title wraps,
    # and a fixed offset would put the accent rule through its second line.
    if first:
        y = canvas.text_block(PDF.MARGIN, y_top, title,
                              PDF.PAGE_W - 2 * PDF.MARGIN,
                              font="Helvetica-Bold", size=20.0, leading=24.0,
                              color=PDF.INK)
        canvas.rect(PDF.MARGIN, y - 4.0, 96.0, 3.5, fill=PDF.ACCENT)
        y -= 14.0
        y = canvas.text_block(PDF.MARGIN, y,
                              "%s   |   %s" % ("STORYBOARD", SUBTITLE),
                              PDF.PAGE_W - 2 * PDF.MARGIN, size=PDF.BODY_PT,
                              leading=LINE, color=PDF.MUTED)
        return y - 6.0
    y = canvas.text_block(PDF.MARGIN, y_top, "%s   |   STORYBOARD" % title,
                          PDF.PAGE_W - 2 * PDF.MARGIN, font="Helvetica-Bold",
                          size=PDF.BODY_PT, leading=LINE, color=PDF.MUTED)
    canvas.line(PDF.MARGIN, y - 6.0, PDF.PAGE_W - PDF.MARGIN, y - 6.0,
                color=PDF.RULE)
    return y - 18.0


def _footer(canvas, page_no):
    canvas.text(PDF.MARGIN, PDF.MARGIN - 4.0, "Page %d" % page_no,
                size=PDF.BODY_PT, color=PDF.MUTED)


def deliver(run_dir, delivery_dir):
    """Write the storyboard PDF into the run's delivery folder.

    One folder per client run, one clear numbered file name.
    Returns the path written.
    """
    package = load(run_dir)
    os.makedirs(delivery_dir, exist_ok=True)
    out = os.path.join(delivery_dir, DELIVERY_NAME)
    write_pdf(captions(package["items"]), out, title=package["title"])
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="storyboard_grid",
        description="Build the storyboard grid PDF for one approved run.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", required=True,
                        help="the run's delivery folder")
    args = parser.parse_args(argv)
    try:
        path = deliver(args.run_dir, args.out)
    except (GridError, PDF.PdfError, AP.ApprovalError, OSError) as exc:
        # ApprovalError is the approval gate's own refusal passed through by
        # load(); it must print as a named failure, never a traceback.
        print("FAIL %s" % exc, file=sys.stderr)
        return 1
    print(path)
    return 0




def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: stage this item's canonical files.

    The one naming scheme lives in delivery_package.contract (``NN - Label.ext``
    per item number). This adapter stages the item's files under those exact
    canonical names via contract.produce_item, so the packaging call copies
    them verbatim and the folder gate opens them unchanged. Signature is the
    packaging contract: produce_delivery(run_dir, item) -> list[Path].
    """
    from delivery_package.contract import produce_item
    staging = Path(run_dir) / "_package" / item.key
    return produce_item(item, staging)

if __name__ == "__main__":
    sys.exit(main())
