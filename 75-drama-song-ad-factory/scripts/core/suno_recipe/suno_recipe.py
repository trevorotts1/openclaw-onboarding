#!/usr/bin/env python3
"""The Suno song recipe (G12): the default for EVERY Suno music style.

Owner order 2026-10-08: the Kiesett and LeAnne Dolce songs landed because
Suno was told plainly what to sing and what to speak. That is now the rule
for every Suno-based style. Only the Velvet Voiceover version (Google voice
over the song) keeps its own flow. stdlib only; no network, no spend.

The four rules (verbatim in SKILL.md):
  1. Suno is told plainly which lines to sing and which to speak.
  2. A repeated sung hook is built from the client's own words.
  3. Singing starts early.
  4. Each take's singing is measured, not taken from its labels.

Every Suno style goes through prepare() (build) and guard_request() (the
seam in music_director). A style with no recipe fails closed.
"""
from __future__ import annotations

import os
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import music_styles as _MS      # noqa: E402
import spoken_share as _SS      # noqa: E402
import sung_hook as _SH         # noqa: E402

TOOL_NAME = "suno_recipe"
TOOL_VERSION = "1.0.0"

RULES = (
    "Suno is told plainly which lines to sing and which to speak.",
    "A repeated sung hook is built from the client's own words.",
    "Singing starts early.",
    "Each take's singing is measured, not taken from its labels.",
)

#: The ONLY style id that skips the recipe: the spoken Google voiceover over
#: the song (core/voice_velvet_echo VELVET_ID). Keep this set to one id.
EXEMPT_STYLE_IDS = frozenset({"velvet_voiceover"})

#: Trevor 5/10 band: first real singing is due by 15% of runtime; within 5
#: points of runtime still passes, within 10 passes with a flag, past that fails.
FIRST_SING_TARGET = 0.15
ACCEPT_PTS, FLAG_PTS = 5, 10
SUNO_STYLE_FIELD_MAX = 1000          # Suno style field character limit
MIN_HOOK_REPEATS = 2


class RecipeError(ValueError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _words(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", str(text).lower())


def is_exempt(style_id):
    return style_id in EXEMPT_STYLE_IDS


def suno_style_ids():
    """Every style that must use the recipe (the music_styles menu)."""
    return tuple(_MS.style_ids())


def _tag(sec):
    return "[%s: %s]" % (sec["delivery"].capitalize(), sec["tag"])


def render_lyrics(sheet):
    """Lyric sheet text with each section tagged Sung or Spoken."""
    return "\n\n".join(_tag(s) + "\n" + "\n".join(s["lines"]) for s in sheet)


_TAG_RE = re.compile(r"^\[(Sung|Spoken): ([^\]]+)\]\s*$")


def parse_lyrics(text):
    """Inverse of render_lyrics. Untagged text yields an empty sheet."""
    sheet, cur = [], None
    for ln in str(text).splitlines():
        m = _TAG_RE.match(ln.strip())
        if m:
            cur = {"tag": m.group(2), "delivery": m.group(1).lower(), "lines": []}
            sheet.append(cur)
        elif cur is not None and ln.strip():
            cur["lines"].append(ln.strip())
    return sheet


def check_lyric_sheet(sheet, client_text, length_s=None):
    """Rules 1-3 on the sheet. Returns a list of errors (empty = pass).

    With length_s (delivered seconds) the I8 count is enforced too: the hook
    is sung exactly sung_hook.hook_count(length_s) times.
    """
    errs = []
    if not sheet:
        return ["no tagged sections: every section must be Sung or Spoken"]
    for s in sheet:
        if s.get("delivery") not in ("sung", "spoken") or not s.get("lines"):
            errs.append("section %r needs delivery sung|spoken and lines"
                        % s.get("tag"))
    if errs:
        return errs
    sung = [s for s in sheet if s["delivery"] == "sung"]
    if not sung:
        return ["no sung section"]
    if sheet.index(sung[0]) > 1:
        errs.append("singing starts late: first sung section is #%d, want "
                    "the first or second" % (sheet.index(sung[0]) + 1))
    keys = [tuple(_words(" ".join(s["lines"]))) for s in sung]
    hooks = [k for k in set(keys) if keys.count(k) >= MIN_HOOK_REPEATS]
    if not hooks:
        return errs + ["no repeated sung hook (same sung lines at least %d "
                       "times)" % MIN_HOOK_REPEATS]
    client = set(_words(client_text))
    if not any(h and set(h) <= client for h in hooks):
        errs.append("repeated hook is not built from the client's own words")
    elif length_s is not None:
        best = max(hooks, key=keys.count)
        errs += _SH.check_sheet_count(sheet, best, length_s)
    return errs


def hook_target(style_id, length_s):
    """I8 hook repeats for a style and delivered length (0 = exempt voiceover)."""
    return 0 if is_exempt(style_id) else _SH.hook_count(length_s)


def style_text(style_id, sheet):
    """Suno style field: the style's base prompt plus the plain sung/spoken map."""
    sung = [s["tag"] for s in sheet if s["delivery"] == "sung"]
    spoken = [s["tag"] for s in sheet if s["delivery"] == "spoken"]
    text = "%s. SUNG: %s. SPOKEN: %s." % (
        _MS.style_prompt(style_id), ", ".join(sung) or "none",
        ", ".join(spoken) or "none")
    if len(text) > SUNO_STYLE_FIELD_MAX:
        raise RecipeError("STYLE_TOO_LONG", "%d chars, limit %d"
                          % (len(text), SUNO_STYLE_FIELD_MAX))
    return text


def check_style_text(text):
    """Rule 1 on the style field: both lists named, the SUNG list non-empty."""
    m = re.search(r"SUNG: (.+?)\. SPOKEN: (.+?)\.?\s*$", str(text))
    if not m or m.group(1).strip() == "none":
        return ["style text has no sung/spoken map (SUNG: ... SPOKEN: ...)"]
    return []


def prepare(style_id, sheet, client_text, length_s=None):
    """THE gate every Suno style goes through. Returns style + lyrics text.

    Exempt (voiceover) -> {"exempt": True}. Unknown id -> fail closed.
    """
    if is_exempt(style_id):
        return {"exempt": True}
    if style_id not in suno_style_ids():
        raise RecipeError("UNKNOWN_STYLE", "%r is not a Suno style and not "
                          "exempt; add it to music_styles" % (style_id,))
    errs = check_lyric_sheet(sheet, client_text, length_s)
    if errs:
        raise RecipeError("LYRICS_REJECTED", "; ".join(errs))
    return {"exempt": False, "style": style_text(style_id, sheet),
            "lyrics": render_lyrics(sheet)}


def guard_request(style_text_, lyrics_text, style_id=None, client_text=None,
                  length_s=None):
    """Seam for music_director.build_generate_request. Raises RecipeError.

    With style_id: the full recipe is enforced (exempt id passes untouched).
    Without: a raw Suno base prompt is a bypass and is refused; any other
    free-form style text is left to the caller (legacy behavior).
    """
    if style_id is None:
        if any(str(style_text_).startswith(_MS.style_prompt(i))
               for i in suno_style_ids()):
            raise RecipeError("RECIPE_BYPASSED", "Suno style used without "
                              "the song recipe; pass style_id and client_text")
        return
    if is_exempt(style_id):
        return
    if style_id not in suno_style_ids():
        raise RecipeError("UNKNOWN_STYLE", repr(style_id))
    errs = check_style_text(style_text_)
    errs += check_lyric_sheet(parse_lyrics(lyrics_text), client_text or "", length_s)
    if errs:
        raise RecipeError("RECIPE_BYPASSED", "; ".join(errs))


def score_take(take, hook_text=None, words=None, length_s=None):
    """Rule 4: judge a take from MEASURED segments only.

    take = {"segments": [{"delivery", "start", "end", "source": "measured"}]}.
    A take with no segments, or any segment not measured (labels), fails.
    Checks the spoken share band (core/spoken_share) and first singing by 15%
    of runtime on the 5/10 band. With hook_text, Suno aligned words and
    length_s, the sung hook count is measured too (I8, Trevor band) and the
    receipt is returned under "hook". Returns {"verdict": PASS|FLAG|FAIL, "reasons"}.
    """
    segs = (take or {}).get("segments")
    if not segs:
        return _res("FAIL", ["take has no measured segments (labels are not a measurement)"])
    if any(s.get("source") != "measured" for s in segs):
        return _res("FAIL", ["take scored from labels: every segment must come from the detector (source=measured)"])
    reasons, flags = [], []
    shares = _SS.measure_share(segs)
    band = _SS.check_share(shares["share"], segs)
    if band["verdict"] == "FAIL":
        reasons += band["reasons"]
    sung = [s["start"] for s in segs if s["delivery"] == "sung"]
    total = shares["total_seconds"]
    if not sung:
        reasons.append("no singing in the take")
    else:
        gap = (min(sung) / total - FIRST_SING_TARGET) * 100.0
        if gap > FLAG_PTS:
            reasons.append("first singing at %.0f%% of runtime, target %.0f%% "
                           "(%.1f points late)" % (min(sung) / total * 100,
                                                   FIRST_SING_TARGET * 100, gap))
        elif gap > ACCEPT_PTS:
            flags.append("first singing %.1f points past target" % gap)
    receipt = None
    if hook_text is not None:
        receipt = _SH.measure(hook_text, words or [], segs, _SH.hook_count(length_s))
        if receipt["verdict"] == "FAIL":
            reasons.append("hook sung %d of %d times %s" % (
                receipt["measured"], receipt["target"], receipt["reason"]))
        elif receipt["verdict"] == "FLAG":
            flags.append("hook sung %d of %d times" % (receipt["measured"], receipt["target"]))
    out = _res("FAIL" if reasons else ("FLAG" if flags else "PASS"), reasons + flags)
    if receipt:
        out["hook"] = receipt
    return out


def _res(verdict, reasons):
    return {"verdict": verdict, "reasons": reasons}
