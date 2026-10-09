#!/usr/bin/env python3
"""character_bible: the CHARACTER BIBLE PDF a client approves before filming.

DEL-02. The bible is not a document written after the run has moved on: the
character's description, background and ethnicity are part of INTAKE.
``questions()`` is what ``intake_preflight.intake.evaluate()`` asks when a brief
declares a character and has not answered every part yet, and ``record()`` is
what the answered brief becomes. Nothing is rendered until intake is complete.

Data comes from ``character_library`` (the per-client save), so a character
answered once is answered for every later ad. ``render()`` lays the text out
beside the CHARACTER IMAGE BIBLE -- the four reference angles every shot of the
character has to match -- and ``write_delivery()`` drops the finished PDF into
the run's delivery folder under a numbered file name.

The PDF is client-facing, so every string that reaches it passes
``assert_client_safe`` first: no product or model names, no money amounts, no
income promises. Standard library only -- no renderer, no third-party package.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_HERE)
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from character_bible import pdf_writer as PW  # noqa: E402

MIN_FONT_PT = PW.MIN_FONT_PT

#: One delivery folder per client run; this unit owns the second numbered file.
DELIVERY_PDF_NAME = "02-character-bible.pdf"

#: The four reference angles, in the order they are laid out.
IMAGE_VIEWS = ("close-up", "side-profile", "three-quarter", "full-standing")

VIEW_LABELS = {
    "close-up": "Close-Up",
    "side-profile": "Side Profile",
    "three-quarter": "Three-Quarter View",
    "full-standing": "Full Standing",
}

#: filename stem -> view, longest key first so "full-standing" beats "full".
VIEW_KEYS = (
    ("full-standing", ("full-standing", "fullstanding", "full-body", "fullbody", "standing", "full")),
    ("three-quarter", ("three-quarter", "threequarter", "3-4", "quarter")),
    ("side-profile", ("side-profile", "sideprofile", "profile", "side")),
    ("close-up", ("close-up", "closeup", "headshot", "portrait", "close")),
)

#: brief key -> the phrase the intake question uses for it.
FIELD_PHRASES = (
    ("character_name", "their name"),
    ("character_description", "one or two sentences describing them"),
    ("character_background",
     "their background: where they are from and what life was like before this story"),
    ("character_ethnicity", "their ethnicity and how they look"),
)

QUESTION_LEAD = ("Tell me about the character who stars in this video, so I can write "
                 "them into the story and build their character bible. I still need: ")

# --- client-facing strings (the test walks every module string through the guard) ---
TITLE = "CHARACTER BIBLE"
IMAGE_TITLE = "CHARACTER IMAGE BIBLE"
SUBTITLE = "Character and image reference"
SECTION_WHO = "WHO THIS IS"
SECTION_BACKGROUND = "BACKGROUND"
SECTION_ETHNICITY = "ETHNICITY AND APPEARANCE"
SECTION_VOICE = "VOICE"
IMAGE_INTRO = ("These four reference angles are what every shot of this character must "
               "match. Approve them before filming begins.")
IMAGE_FOOTNOTE = "Same face, same build, same wardrobe in every shot."
PLACEHOLDER_LINES = ("Not supplied yet", "Send a reference for this angle.")
FOOTER_LEFT = "Character bible - prepared for your approval. Nothing is filmed until you say yes."
PENDING = "Not answered yet."

# --- the client-safety guard -------------------------------------------------
CURRENCY_RE = re.compile(r"[$€£¥]\s*\d|\d\s*([$€£¥]|\b(?:dollars|usd)\b)", re.I)

#: Income promises never appear in a client-facing PDF.
BANNED_PHRASES = (
    "guaranteed income", "passive income", "income promise", "guaranteed profit",
    "make money fast", "money fast", "risk-free", "risk free", "no risk",
    "financial freedom", "earn while you sleep", "easy money", "free money",
    "get rich", "six figures", "recurring income", "repeatable income",
    "proven system", "works every time",
)

#: Model, tool and product names never appear in a client-facing PDF. The paid
#: job host is listed by its bare word so this file never carries a KIE
#: endpoint string (qc-no-direct-kie.sh owns that string, not this one).
BANNED_TOKENS = (
    "openrouter", "ollama", "minimax", "seedance", "suno", "openclaw", "chatgpt",
    "openai", "anthropic", "claude", "sonnet", "opus", "gemini", "deepseek",
    "qwen", "kimi", "midjourney", "elevenlabs", "ffmpeg", "telegram", "kie",
    "kling", "veo", "llm",
)

_TOKEN_RE = {t: re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(t), re.I)
             for t in BANNED_TOKENS}


class BibleError(ValueError):
    """A refusal this unit owns. The message is plain English, for the client path."""


def unsafe_reason(text):
    """Why ``text`` may not go into a client PDF, or None when it is clean."""
    s = str(text or "")
    if CURRENCY_RE.search(s):
        return "money amount"
    low = s.lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            return "income promise (%s)" % phrase
    for token, rx in _TOKEN_RE.items():
        if rx.search(s):
            return "product or model name (%s)" % token
    return None


def assert_client_safe(text, where="text"):
    """Refuse a string that would put money, a product name or a promise in the PDF."""
    why = unsafe_reason(text)
    if why:
        raise BibleError("CLIENT_TEXT_REFUSED: %s in %s may not appear in a "
                         "client-facing PDF (%s)." % (why, where, str(text)[:60]))
    return text


# --- intake ------------------------------------------------------------------
def _truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v == 1
    return str(v or "").strip().lower() in (
        "1", "new", "new character", "create", "create new", "create a new character", "yes")


def _value(v):
    if isinstance(v, dict):
        for k in ("value", "text", "n"):
            if v.get(k) is not None:
                return v[k]
        return None
    return v


def declared(brief):
    """True when the brief is building a NEW character (the CHARACTER card answer)
    or already carries character fields that intake must finish."""
    if not isinstance(brief, dict):
        return False
    if any(str(brief.get(k) or "").strip() for k, _ph in FIELD_PHRASES):
        return True
    if "character_new" in brief:
        return _truthy(brief.get("character_new"))
    if "saved_character" in brief:
        return _truthy(_value(brief.get("saved_character")))
    return False


def missing_fields(brief):
    """The character parts the brief has not answered, in intake order."""
    if not isinstance(brief, dict) or not declared(brief):
        return []
    return [(k, ph) for k, ph in FIELD_PHRASES
            if not str(brief.get(k) or "").strip()]


def questions(brief):
    """One bundled intake question for every missing character part, or [].

    Same shape as ``missing_essentials`` (``{"id", "question"}``), so intake can
    hand it straight to the envelope. A complete character asks nothing.
    """
    miss = missing_fields(brief)
    if not miss:
        return []
    parts = [ph for _k, ph in miss]
    if len(parts) == 1:
        body = parts[0]
    elif len(parts) == 2:
        body = parts[0] + " and " + parts[1]
    else:
        body = ", ".join(parts[:-1]) + ", and " + parts[-1]
    return [{"id": "character",
             "question": QUESTION_LEAD + body + "."}]


def record(brief, voice_notes="", reference_images=None):
    """The bible record an answered brief becomes. BibleError when incomplete."""
    miss = missing_fields(brief)
    if miss:
        raise BibleError("MISSING_CHARACTER: still need %s"
                         % ", ".join(ph for _k, ph in miss))
    rec = {k: str(brief.get(k) or "").strip() for k, _ph in FIELD_PHRASES}
    rec["voice_notes"] = str(voice_notes or brief.get("character_voice_notes") or "").strip()
    imgs = reference_images
    if imgs is None:
        imgs = brief.get("character_reference_images") or []
    rec["reference_images"] = [str(p) for p in imgs]
    for key in ("character_name", "character_description", "character_background",
                "character_ethnicity", "voice_notes"):
        assert_client_safe(rec.get(key, ""), key)
    return rec


def record_from_saved(client_dir, name, brief=None):
    """Reuse ``character_library``: a saved character fills the brief, the brief wins."""
    from character_library import character_library as CL  # noqa: PLC0415
    saved = CL.brief_fields(CL.get_character(client_dir, name))
    merged = dict(saved)
    merged.update({k: v for k, v in (brief or {}).items()
                   if str(v or "").strip()})
    return record(merged)


# --- image bible -------------------------------------------------------------
def _view_of(stem):
    s = re.sub(r"[^a-z0-9]+", "-", str(stem).lower()).strip("-")
    for view, keys in VIEW_KEYS:
        for k in keys:
            if s == k or s.startswith(k + "-"):
                return view
    return None


def resolve_images(sources):
    """Map view -> image path from a dict, a list of paths, or a directory.

    Unrecognised files are ignored: only the four named angles are laid out.
    """
    out = {}
    if isinstance(sources, dict):
        for k, v in sources.items():
            view = _view_of(k)
            if view and v:
                out[view] = str(v)
        return out
    if isinstance(sources, str):
        sources = [sources]
    files = []
    for src in sources or []:
        if os.path.isdir(src):
            files += [os.path.join(src, n) for n in sorted(os.listdir(src))
                      if os.path.isfile(os.path.join(src, n))]
        elif os.path.isfile(src):
            files.append(src)
    for path in files:
        view = _view_of(os.path.splitext(os.path.basename(path))[0])
        if view and view not in out:
            out[view] = path
    return out


# --- layout ------------------------------------------------------------------
TEAL = (0.059, 0.298, 0.361)
GOLD = (0.788, 0.592, 0.000)
INK = (0.102, 0.102, 0.102)
GREY = (0.360, 0.396, 0.420)
PANEL = (0.965, 0.972, 0.976)
HAIRLINE = (0.840, 0.862, 0.878)

X0, WIDTH = PW.MARGIN, PW.PAGE_W - 2 * PW.MARGIN


def _header(doc, title, subtitle):
    doc.fill_rect(0, PW.PAGE_H - 72, PW.PAGE_W, 72, TEAL)
    doc.text(X0, PW.PAGE_H - 44, title, 20, "bold", (1, 1, 1))
    doc.text(PW.PAGE_W - PW.MARGIN - PW.text_width(subtitle, 12, "regular"),
             PW.PAGE_H - 44, subtitle, 12, "regular", (0.87, 0.93, 0.95))
    doc.fill_rect(0, PW.PAGE_H - 76, PW.PAGE_W, 4, GOLD)
    return PW.PAGE_H - 102


def _section(doc, y, label, body, page_title):
    if y < 96:
        doc.page()
        y = _header(doc, page_title, SUBTITLE)
    doc.text(X0, y, label, 12, "bold", TEAL)
    y -= 19
    y = doc.paragraph(X0, y, body, 13, WIDTH, 18.4, "regular", INK)
    return y - 12


def render(rec, images, out_path):
    """Write the two-page bible (text, then the image bible) to ``out_path``."""
    images = images or {}
    for view in IMAGE_VIEWS:
        if images.get(view) and not os.path.isfile(images[view]):
            raise BibleError("IMAGE_NOT_FOUND: no %s reference at %s"
                             % (VIEW_LABELS[view], images[view]))
    doc = PW.Doc()

    # --- page 1: the character ---------------------------------------------
    y = _header(doc, TITLE, SUBTITLE)
    doc.text(X0, y, str(rec.get("character_name") or ""), 26, "bold", INK)
    y -= 38
    y = _section(doc, y, SECTION_WHO, rec.get("character_description") or PENDING, TITLE)
    y = _section(doc, y, SECTION_BACKGROUND, rec.get("character_background") or PENDING, TITLE)
    y = _section(doc, y, SECTION_ETHNICITY, rec.get("character_ethnicity") or PENDING, TITLE)
    if str(rec.get("voice_notes") or "").strip():
        y = _section(doc, y, SECTION_VOICE, rec["voice_notes"], TITLE)

    # --- page 2: the image bible -------------------------------------------
    doc.page()
    y = _header(doc, IMAGE_TITLE, SUBTITLE)
    y = doc.paragraph(X0, y, IMAGE_INTRO, 13, WIDTH, 18.4, "regular", INK) - 6
    doc.text(X0, y, IMAGE_FOOTNOTE, 12, "regular", GREY)

    cell_w, cell_h, gap = 240.0, 236.0, 20.0
    top = 630.0
    for i, view in enumerate(IMAGE_VIEWS):
        col, row = i % 2, i // 2
        cx = X0 + col * (cell_w + gap)
        cy = top - row * (cell_h + gap) - cell_h
        doc.fill_rect(cx, cy, cell_w, cell_h, PANEL)
        doc.stroke_rect(cx, cy, cell_w, cell_h, HAIRLINE, 1.0)
        path = images.get(view)
        if path:
            try:
                doc.image(path, cx + 10, cy + 40, cell_w - 20, cell_h - 50)
            except PW.PdfError as exc:
                raise BibleError(str(exc))
        else:
            doc.placeholder(cx + 10, cy + 40, cell_w - 20, cell_h - 50, PLACEHOLDER_LINES)
        doc.text(cx + 12, cy + 16, VIEW_LABELS[view], 12, "bold", TEAL)

    doc.draw_footers(FOOTER_LEFT)
    doc.save(out_path)
    PW.check_font_floor(out_path)          # output-side gate, never the author's intent
    return out_path


def write_delivery(delivery_dir, rec, images=None):
    """Render into the run's delivery folder; returns the finished path."""
    os.makedirs(delivery_dir, exist_ok=True)
    path = os.path.join(delivery_dir, DELIVERY_PDF_NAME)
    return render(rec, images if isinstance(images, dict) else resolve_images(images), path)


# --- command line ------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Character bible questions and PDF.")
    sub = ap.add_subparsers(dest="cmd")
    q = sub.add_parser("questions", help="Intake questions for an incomplete character.")
    q.add_argument("--brief", required=True, help="Brief JSON file.")
    r = sub.add_parser("render", help="Write the character bible PDF into a delivery folder.")
    r.add_argument("--brief", required=True, help="Brief JSON file (character fields).")
    r.add_argument("--delivery", required=True, help="The run's delivery folder.")
    r.add_argument("--image", action="append", default=[],
                   help="VIEW=PATH, or a path; repeatable. Directories are scanned.")
    r.add_argument("--voice-notes", default="")
    a = ap.parse_args(argv)
    with open(a.brief, encoding="utf-8") as fh:
        brief = json.load(fh)
    if a.cmd == "questions":
        print(json.dumps(questions(brief), indent=2))
        return 0
    if a.cmd == "render":
        rec = record(brief, voice_notes=a.voice_notes)
        path = write_delivery(a.delivery, rec, a.image)
        print(json.dumps({"pdf": path, "views": sorted(resolve_images(a.image))}))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
