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

WW-27 adds the ENSEMBLE CAST model and its pre-generation gate to this
module: the cast decision precedes drafting, every character carries a full
treatment and a Suno voice direction, a villain or foil speaks and is
answered, undeclared speakers and a single-voice ensemble style are
refused, and the take stays ONE full-song track. The gate judges the
script and the serialized payload only -- audio gate D5 alone confirms the
delivered voices.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_HERE)
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from character_bible import pdf_writer as PW  # noqa: E402

MIN_FONT_PT = PW.MIN_FONT_PT

#: One delivery folder per client run; this unit owns the second numbered file.
#: The name is the ONE naming scheme, taken verbatim from the DEL-13 contract
#: (``NN - Label.ext``) -- never reformatted here, so the two cannot drift.
from delivery_package.contract import ITEMS_BY_KEY as _ITEMS  # noqa: E402

DELIVERY_PDF_NAME = _ITEMS["character_bible"].files[0]

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
    """Render into the run's delivery folder; returns the PDF path.

    DEL-13 item 02 is BOTH contract files: the numbered PDF and the image
    directory beside it (``02 - Character Bible Images``) holding the same
    reference pictures the layout used, as separate full files -- the
    client's consistency set ships on its own, not only embedded in the
    PDF. This is the real deliver path for the whole item: no reference
    picture in the run, no item (BibleError), never a placeholder.
    """
    os.makedirs(delivery_dir, exist_ok=True)
    if images is None:
        images = rec.get("reference_images") or []
    resolved = images if isinstance(images, dict) else resolve_images(images)
    path = os.path.join(delivery_dir, DELIVERY_PDF_NAME)
    pdf = render(rec, resolved, path)
    img_dir = os.path.join(delivery_dir, _ITEMS["character_bible"].files[1])
    os.makedirs(img_dir, exist_ok=True)
    shipped = 0
    for view in sorted(resolved):
        src = resolved.get(view)
        if not src or not os.path.isfile(src) or os.path.getsize(src) <= 0:
            continue
        ext = os.path.splitext(src)[1].lower() or ".png"
        shutil.copy2(src, os.path.join(img_dir, view + ext))
        shipped += 1
    if not shipped:
        raise BibleError("NO_REFERENCE_IMAGES: %s has no reference picture "
                         "to ship beside the bible PDF"
                         % (rec.get("character_name") or "the character"))
    return pdf


# ---- WW-27: the ensemble cast model and the distinct-voice gate -------------
#
# WW-27 (2026-10-11): the CAST DECISION precedes drafting. Multiple characters
# are the DEFAULT and the count follows the conflict; a single-voice cast is
# legal only when the brief declares it. Every declared character carries a
# complete treatment -- name, role, want, wound, relationships, consequential
# action, voice -- and a Suno voice direction of register, timbre, articulation,
# delivery, emotional progression and version treatment. At least one villain or
# foil SPEAKS and receives a consequential reply; a non-person antagonist is
# permitted only with a speaking foil. A bracket in the sheet that names a
# character nobody declared is REFUSED, and an ensemble whose FINAL style still
# commands a single voice ("A single female voice.") is REFUSED. One full-song
# track is kept: a stitched voice pack is REFUSED.
#
# This is a PRE-GENERATION check on the script and the serialized payload --
# never a delivered-audio gate. Audio gate D5 alone confirms the delivered
# voices. Every number here is a NEW ACCEPTANCE RULE, not a measured limit and
# never a number Trevor set. Same as before: a check that only fires on a
# hand-built dictionary is not a guard, so the seam is checked at the real call
# sites (suno_recipe.build_request, music_director.build_generate_request,
# song_contract.check_sheet).

CAST_SCHEMA = "blackceo.ensemble-cast/v1"

TOOL_NAME = "character_bible"

CAST_MODES = ("ensemble", "single")
DEFAULT_CAST_MODE = "ensemble"      # PROPOSED: multiple characters by default
MIN_ENSEMBLE = 2                    # PROPOSED: an ensemble is two or more
CAST_ROLES = ("protagonist", "villain", "foil", "antagonist", "support", "narrator")
#: A role that OPPOSES the protagonist; one of these must speak.
OPPOSING_ROLES = ("villain", "foil", "antagonist")
CAST_FIELDS = ("name", "role", "want", "wound", "relationships",
               "consequential_action", "voice")
#: The character's SUNO VOICE direction: register, timbre, articulation,
#: delivery, emotional progression and version treatment. The brief key is
#: ``voice_direction`` -- the name is scrubbed because this module's own
#: client-safety walker refuses a PUBLIC string constant that carries a product
#: or model name, and the recipe host's name is one of them.
VOICE_DIRECTION_FIELDS = ("register", "timbre", "articulation", "delivery",
                          "emotional_progression", "version_treatment")
CHARACTER_FIELDS = CAST_FIELDS + ("voice_direction",)

CODE_CAST_NOT_ENSEMBLE = "CAST_NOT_ENSEMBLE"
CODE_CAST_INCOMPLETE = "CAST_INCOMPLETE"
CODE_CAST_VOICE_INCOMPLETE = "CAST_VOICE_INCOMPLETE"
CODE_CAST_ROLE_UNKNOWN = "CAST_ROLE_UNKNOWN"
CODE_CAST_NO_OPPOSING_VOICE = "CAST_NO_OPPOSING_VOICE"
CODE_CAST_OPPONENT_SILENT = "CAST_OPPONENT_SILENT"
CODE_CAST_NO_CONSEQUENTIAL_REPLY = "CAST_NO_CONSEQUENTIAL_REPLY"
CODE_CAST_VOICES_IDENTICAL = "CAST_VOICES_IDENTICAL"
CODE_SPEAKER_UNDECLARED = "SPEAKER_UNDECLARED"
CODE_ENSEMBLE_SINGLE_VOICE_STYLE = "ENSEMBLE_SINGLE_VOICE_STYLE"
CODE_VOICE_PACK_STITCHED = "VOICE_PACK_STITCHED"

#: A style that COMMANDS one voice is refused for an ensemble cast. Matched on
#: the FINAL serialized request["input"]["style"]. The plan's literal case is
#: "A single female voice."
#: ponytail: this is the command class the plan names, not every possible
#: single-voice phrasing; extend the alternation when a built style ships one.
_SINGLE_VOICE_RE = re.compile(
    r"\b(?:a|one|single|only\s+one|just\s+one)\s+(?:single\s+|only\s+|solo\s+)?"
    r"(?:female|male|woman|man|woman's|man's|gender)?\s*(?:lead\s+|solo\s+)?"
    r"(?:voice|vocal|singer)\b"
    r"|\bsolo\s+(?:female|male|woman|man)\s+(?:voice|vocal)\b"
    r"|\bsingle\s+(?:lead\s+)?voice\b"
    r"|\bonly\s+one\s+voice\b", re.I)


def _present(v):
    """True when a cast field carries a value: a non-empty string, list or
    mapping, a True flag, or a number. False for None, "", [], {} and False."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, (list, tuple, dict, set)):
        return len(v) > 0
    return bool(str(v or "").strip())


def _norm_name(name):
    """A character name normalized for matching: case, spacing, separators."""
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


def _recipe():
    """suno_recipe, whether it is a package or the bare module on sys.path.

    ONE tag grammar (FU-U1/FU-U5): the ensemble gate reads brackets through the
    recipe's own reader, never a second parser."""
    import suno_recipe as _R
    return getattr(_R, "suno_recipe", _R)


def _declared_mode(brief):
    """The brief's DECLARED cast mode: "ensemble" | "single" | None when it
    declares none (the default then applies)."""
    b = brief if isinstance(brief, dict) else {}
    if b.get("schema") == CAST_SCHEMA:
        v = str(b.get("mode") or "").strip().lower()
        return v if v in CAST_MODES else None
    for key in ("cast_mode", "cast_decision"):
        v = b.get(key)
        if isinstance(v, dict):
            v = v.get("mode")
        v = str(v or "").strip().lower()
        if v in CAST_MODES:
            return v
    c = b.get("cast")
    if isinstance(c, dict):
        v = str(c.get("mode") or "").strip().lower()
        if v in CAST_MODES:
            return v
    return None


def cast_decision(brief):
    """THE cast decision, taken BEFORE drafting. Multiple characters by default.

    "Count follows the conflict": with no explicit mode the decision is an
    ensemble of ``MIN_ENSEMBLE`` or more, and "single" is honoured only when the
    brief declares it. PRE-GENERATION script decision; D5 alone confirms the
    delivered voices. PROPOSED numbers, never a measured limit.
    """
    b = brief if isinstance(brief, dict) else {}
    explicit = _declared_mode(b)
    n = len(b.get("characters") or [])
    return {"schema": CAST_SCHEMA, "mode": explicit or DEFAULT_CAST_MODE,
            "declared_mode": explicit, "default": explicit is None,
            "declared_cast": bool(n) or explicit is not None,
            "characters_n": n, "min_characters": MIN_ENSEMBLE,
            "reason": ("multiple characters are the default; the count follows "
                       "the conflict" if (explicit or DEFAULT_CAST_MODE) == "ensemble"
                       else "the brief declares a single-voice cast")}


def resolve_cast(brief_or_cast):
    """The ensemble cast record a brief (or a resolved cast) becomes.

    ONE shape: {"mode", "decision", "characters": [entry, ...]}. Each entry
    carries the seven ``CAST_FIELDS``, the six ``VOICE_DIRECTION_FIELDS``, its gender
    and its speech facts (``person`` / ``speaks`` / ``reply_to``), plus the exact
    fields it is MISSING. Order is the brief's; nothing is invented, nothing is
    dropped, and re-resolving a resolved cast changes nothing.
    """
    src = brief_or_cast if isinstance(brief_or_cast, dict) else {}
    explicit = _declared_mode(src)
    chars = []
    for item in (src.get("characters") or []):
        raw = item if isinstance(item, dict) else {"name": item}
        entry = {k: raw.get(k) for k in CAST_FIELDS}
        entry["name"] = str(raw.get("name") or "").strip()
        entry["role"] = str(raw.get("role") or "").strip().lower()
        sv = raw.get("voice_direction")
        sv = sv if isinstance(sv, dict) else {}
        entry["voice_direction"] = {k: sv.get(k) for k in VOICE_DIRECTION_FIELDS}
        entry["gender"] = raw.get("gender")
        entry["person"] = raw.get("person")
        entry["speaks"] = raw.get("speaks")
        entry["reply_to"] = raw.get("reply_to")
        entry["missing"] = [k for k in CAST_FIELDS if not _present(raw.get(k))]
        entry["voice_direction_missing"] = [k for k in VOICE_DIRECTION_FIELDS
                                       if not _present(sv.get(k))]
        chars.append(entry)
    mode = explicit or DEFAULT_CAST_MODE
    return {"schema": CAST_SCHEMA, "mode": mode, "decision": mode,
            "mode_declared": explicit, "declared": bool(chars) or explicit is not None,
            "characters": chars, "min_characters": MIN_ENSEMBLE}


def speaker_turns(sheet_text):
    """The sheet's speakers IN ORDER, each with the lines that follow it.

    ONE tag grammar: the bracket reader is suno_recipe's (``parse_voice_tags``),
    never a second parser. A bracket that names nobody ([Hook], [Intro], [End])
    starts no turn, so an unnamed section never steals a character's line.
    """
    R = _recipe()
    turns, cur = [], None
    for raw in str(sheet_text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("[") and s.endswith("]"):
            tags = R.parse_voice_tags(s)
            cur = None
            if tags and tags[0]["name"]:
                cur = {"speaker": tags[0]["name"], "gender": tags[0]["gender"],
                       "tag": str(tags[0]["tag"])[:60], "lines": []}
                turns.append(cur)
            continue
        if cur is not None:
            cur["lines"].append(s)
    return turns


def traded_replies(turns, opponents):
    """The first OPPOSING speaker whose NEXT named turn is another character.

    WW-27's "traded replies": a villain or foil speaks AND receives a
    consequential reply. The reply is the next named turn in the sheet, by a
    DIFFERENT declared character. Returns {opponent, reply, ...} or None.
    """
    opp = {_norm_name(n) for n in opponents or []}
    for i, t in enumerate(turns or []):
        if _norm_name(t.get("speaker")) not in opp:
            continue
        for nxt in turns[i + 1:]:
            if _norm_name(nxt.get("speaker")) != _norm_name(t.get("speaker")):
                return {"opponent": t["speaker"], "reply": nxt["speaker"],
                        "opponent_lines": len(t.get("lines") or []),
                        "reply_lines": len(nxt.get("lines") or [])}
    return None


def cast_reasons(brief_or_cast, sheet_text=None, style_text=None, take=None):
    """Why the cast, the script or the payload is not a developed ensemble.

    [] = it is. PRE-GENERATION: this judges the cast record, the sheet's speaker
    brackets and the FINAL style text -- never audio. Every refusal carries its
    own named code:

      CAST_NOT_ENSEMBLE             an ensemble decision with fewer than two
      CAST_INCOMPLETE               a character missing a treatment field
      CAST_VOICE_INCOMPLETE         a character missing a Suno voice field
      CAST_ROLE_UNKNOWN             a role outside CAST_ROLES
      CAST_NO_OPPOSING_VOICE        no villain/foil, or a non-person antagonist
                                    with no speaking foil
      CAST_OPPONENT_SILENT          the villain/foil never speaks
      CAST_NO_CONSEQUENTIAL_REPLY   it speaks and no one answers it
      CAST_VOICES_IDENTICAL         two characters share ONE Suno voice direction
      SPEAKER_UNDECLARED            a sheet bracket names nobody the cast holds
      ENSEMBLE_SINGLE_VOICE_STYLE   an ensemble style commanding one voice
      VOICE_PACK_STITCHED           a stitched voice pack, not one full song

    With no cast record at all the ensemble-count rule never fires (there is no
    cast to count); an undeclared SPEAKER still refuses, because a name in the
    script that nobody declared can never be cast.
    """
    cast = resolve_cast(brief_or_cast)
    chars, mode = cast["characters"], cast["mode"]
    reasons = []
    # the cast decision: multiple characters by default, count follows conflict
    if cast["declared"] and mode == "ensemble" and len(chars) < MIN_ENSEMBLE:
        reasons.append("%s: the cast decision is an ensemble (%d characters by "
                       "default, the count follows the conflict) and %d character(s) "
                       "is declared" % (CODE_CAST_NOT_ENSEMBLE, MIN_ENSEMBLE, len(chars)))
    # every declared character carries the complete treatment
    for c in chars:
        who = c["name"] or "<unnamed character>"
        if c["missing"]:
            reasons.append("%s: %s is missing %s"
                           % (CODE_CAST_INCOMPLETE, who, ", ".join(c["missing"])))
        if c["voice_direction_missing"]:
            reasons.append("%s: %s's Suno voice is missing %s"
                           % (CODE_CAST_VOICE_INCOMPLETE, who,
                              ", ".join(c["voice_direction_missing"])))
        if c["role"] and c["role"] not in CAST_ROLES:
            reasons.append("%s: %s's role is %r, not one of %s"
                           % (CODE_CAST_ROLE_UNKNOWN, who, c["role"],
                              ", ".join(CAST_ROLES)))
    # The SPEAKING rules are SCRIPT rules: they need the sheet. Before the
    # script exists (the cast decision that precedes drafting) only the cast
    # record is judged, plus any explicit ``speaks`` declaration.
    has_script = sheet_text is not None
    turns = speaker_turns(sheet_text) if has_script else []
    spoken = {_norm_name(t["speaker"]) for t in turns if t.get("lines")}
    opposing = [c for c in chars if c["role"] in OPPOSING_ROLES]
    if chars:
        speaking = [c for c in chars
                    if c["speaks"] or (has_script and _norm_name(c["name"]) in spoken)]
        # A NON-PERSON antagonist never speaks: its opposition is VOICED by a
        # person — a villain or a foil — so only the person members are asked to
        # speak and to be answered.
        person_opp = [c for c in opposing if c["person"] is not False]
        spokes = [c for c in person_opp if c in speaking]
        nonperson = [c for c in opposing if c["person"] is False]
        if not opposing:
            reasons.append("%s: the cast declares no villain or foil; at least one "
                           "opposition voice is required (roles: %s)"
                           % (CODE_CAST_NO_OPPOSING_VOICE, ", ".join(CAST_ROLES)))
        else:
            if nonperson and not spokes:
                reasons.append("%s: the antagonist %s is not a person and no speaking "
                               "villain or foil voices it; a non-person antagonist needs "
                               "a speaking foil"
                               % (CODE_CAST_NO_OPPOSING_VOICE,
                                  ", ".join(c["name"] or "<unnamed>" for c in nonperson)))
            if has_script and not spokes:
                reasons.append("%s: the villain/foil %s never speaks; at least one "
                               "villain or foil must speak"
                               % (CODE_CAST_OPPONENT_SILENT,
                                  ", ".join(c["name"] or "<unnamed>" for c in person_opp
                                            or opposing)))
            elif has_script and traded_replies(
                    turns, [c["name"] for c in person_opp]) is None:
                reasons.append("%s: %s speaks but no other declared character answers "
                               "it; the villain/foil must receive a consequential reply"
                               % (CODE_CAST_NO_CONSEQUENTIAL_REPLY,
                                  spokes[0]["name"] or "<unnamed>"))
    # contrasting vocal directions: two characters never share ONE Suno voice
    seen = {}
    for c in chars:
        key = tuple(str(c["voice_direction"].get(k) or "").strip().lower()
                    for k in VOICE_DIRECTION_FIELDS)
        if not any(key):
            continue
        who = c["name"] or "<unnamed character>"
        if key in seen:
            if seen[key] is not None:
                reasons.append("%s: %s and %s carry the SAME Suno voice direction "
                               "(%s); the ensemble needs contrasting vocal directions"
                               % (CODE_CAST_VOICES_IDENTICAL, seen[key], who,
                                  ", ".join(VOICE_DIRECTION_FIELDS)))
                seen[key] = None
            continue
        seen[key] = who
    # undeclared speakers: a bracket naming a character the cast does not hold
    declared = {_norm_name(c["name"]) for c in chars}
    for t in (_recipe().parse_voice_tags(sheet_text) if sheet_text else []):
        n = t.get("name")
        if n and _norm_name(n) not in declared:
            reasons.append("%s: the sheet tags %r, who is not a declared character (%s)"
                           % (CODE_SPEAKER_UNDECLARED, n,
                              ", ".join(c["name"] for c in chars)
                              or "no cast is declared"))
    # an ensemble style that still commands ONE voice
    if mode == "ensemble" and len(chars) >= MIN_ENSEMBLE and style_text:
        m = _SINGLE_VOICE_RE.search(str(style_text))
        if m is not None:
            reasons.append("%s: the cast is an ensemble of %d characters but the style "
                           "commands a single voice (%r); an ensemble style names every "
                           "voice instead"
                           % (CODE_ENSEMBLE_SINGLE_VOICE_STYLE, len(chars), m.group(0)))
    # one full-song track: no stitched voice-pack revival
    if isinstance(take, dict):
        pack = take.get("voice_pack") or take.get("designated_voice") or take.get("stitched")
        tracks = take.get("tracks")
        if pack or (isinstance(tracks, int) and not isinstance(tracks, bool) and tracks > 1):
            reasons.append("%s: the take is a stitched voice pack (%s), not one full-song "
                           "track; the stitched voice-pack revival is not approved"
                           % (CODE_VOICE_PACK_STITCHED,
                              pack or ("%r tracks" % (tracks,))))
    return reasons


def check_cast(brief_or_cast, sheet_text=None, style_text=None, take=None):
    """The WW-27 receipt for one cast, script and payload. PASS only when
    ``cast_reasons`` is empty. Carries zero purchases and measures no audio, so
    it is not a sixth delivered-audio gate: D5 alone confirms the voices."""
    cast = resolve_cast(brief_or_cast)
    reasons = cast_reasons(brief_or_cast, sheet_text=sheet_text,
                           style_text=style_text, take=take)
    turns = speaker_turns(sheet_text) if sheet_text else []
    names = [c["name"] for c in cast["characters"]]
    voices = {tuple(str(c["voice_direction"].get(k) or "").strip().lower()
                    for k in VOICE_DIRECTION_FIELDS) for c in cast["characters"]}
    return {"tool": TOOL_NAME, "schema": CAST_SCHEMA,
            "verdict": "PASS" if not reasons else "FAIL",
            "reason_code": reasons[0].split(":")[0] if reasons else "ENSEMBLE_CAST_OK",
            "reasons": reasons, "blocked": bool(reasons), "purchases": 0,
            "measures_no_audio": True,
            "decision": cast["decision"], "mode": cast["mode"],
            "mode_declared": cast["mode_declared"],
            "characters": names, "characters_n": len(names),
            "fields": list(CHARACTER_FIELDS), "voice_direction_fields": list(VOICE_DIRECTION_FIELDS),
            "speakers": [t["speaker"] for t in turns],
            "traded_replies": (traded_replies(
                turns, [c["name"] for c in cast["characters"]
                        if c["role"] in OPPOSING_ROLES]) if turns else None),
            "contrast": len(voices),
            "detail": ("; ".join(reasons) if reasons else
                       "%d declared character(s); the ensemble cast is complete"
                       % len(names))}


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




def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: the REAL DEL-02 deliver path (bible + images).

    Reads the run's character brief (``character/brief.json``: the answered
    character fields plus ``character_reference_images``), turns it into the
    bible record and calls ``write_delivery`` -- the same entry the CLI
    renders with. That one deliver path writes BOTH of this item's contract
    files: the numbered PDF and the ``02 - Character Bible Images``
    directory of the same reference pictures. Fixture bytes are never
    written: ``contract.produce_item`` is test-only and no deliver path
    imports it. Signature: produce_delivery(run_dir, item) -> list[Path].
    """
    from delivery_package import run_inputs as RI
    out = RI.delivery_dir(run_dir)
    brief = RI.load_json(run_dir, os.path.join("character", "brief.json"))
    rec = record(brief)
    write_delivery(str(out), rec)
    return RI.stage(item, out)

if __name__ == "__main__":
    sys.exit(main())
