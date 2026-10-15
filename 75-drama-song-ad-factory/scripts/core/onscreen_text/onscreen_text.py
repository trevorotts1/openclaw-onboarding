#!/usr/bin/env python3
"""onscreen_text.py: no words inside generated pictures by default (SPEC A6).

Decided (LEDGER 13:15) — the three rungs of the words ladder:

  1. DEFAULT — no words at all. Every Agnes still prompt and every Agnes video
     prompt carries ``no_text_block()``. Nothing is baked, so nothing can be
     misspelled (Trial A: 30 sampled frames of the final read no words).
  2. BAKE — a shot that truly needs one word (a sign, a book title) may bake it
     into the still, but only after OCR read the still back and matched the
     EXACT words (``verify_still``), up to ``MAX_TRIES`` free tries.
  3. OVERLAY — the decided fallback, never a re-bake and never sent back to the
     client: the shot is made without the words and
     ``final_assembler.captions_burn.overlay_excerpt`` draws them at assembly.
     The receipt says ``TEXT_OVERLAID``.

Fail closed everywhere: tesseract missing -> ``OCR_UNAVAILABLE``, never a PASS.
The shipped default extractor of frame_text reads no pixels, so a picture
nobody read must never look like a clean read — an empty OCR read is a FAIL,
not an absence of words. The OCR read itself goes through load_governor
(SPEC A12: heavy local work is gated).

Inert until wired: this module changes no pipeline on its own. The Agnes path
calls it only for a run carrying ``agnes.answer == "yes"``, and the assembler
keeps today's behaviour until the Agnes wiring lands. At import the tesseract
extractor is registered with frame_text (``register_extractor``) so the frame
gate can read real pixels with no edit to frame_text.py; ``REGISTERED`` says
whether that happened.

stdlib only, no network, no spend. The OCR binary is optional forever.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess

# Skill 75 load governor: every heavy local job goes through it (see load_governor/).
import os as _gos, sys as _gsys
_gcore = _gos.path.abspath(_gos.path.join(_gos.path.dirname(__file__), '..'))
if _gcore not in _gsys.path:
    _gsys.path.insert(0, _gcore)
import load_governor as _LG  # noqa: E402

TOOL_NAME = "onscreen_text"
TOOL_VERSION = "1.0.0"

#: The block every Agnes picture prompt carries (SPEC A6, exact wording).
NO_TEXT_BLOCK = "No words, letters, numbers, logos or signage anywhere in the image."

#: How many verified bakes a shot gets before the words are overlaid (SPEC A6).
MAX_TRIES = 3

#: The one OCR engine. Optional forever: absent -> OCR_UNAVAILABLE, never PASS.
ENGINE = "tesseract"
PSM = "11"          # sparse text: what written words are in this picture

# Receipt words.
TEXT_BAKED = "TEXT_BAKED"
TEXT_OVERLAID = "TEXT_OVERLAID"

# Reason codes.
OCR_UNAVAILABLE = "OCR_UNAVAILABLE"        # no engine, no read, never a PASS
OCR_FAILED = "OCR_FAILED"                  # the read crashed or mis-shaped
STILL_UNAVAILABLE = "STILL_UNAVAILABLE"    # no file to read
TEXT_NOT_VERIFIED = "TEXT_NOT_VERIFIED"    # read back, not the exact words
BAD_INPUT = "BAD_INPUT"

# Verdicts (never "PASS by default").
VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_UNAVAILABLE = "UNAVAILABLE"


class OnscreenTextError(Exception):
    """Fail-closed error carrying its reason code."""
    def __init__(self, code, message):
        Exception.__init__(self, "%s: %s" % (code, message))
        self.code = code


# frame_text's own error class is the second base when it loaded, so an
# extractor that cannot read pixels raises a code frame_text re-raises
# verbatim instead of wrapping it as a crashed extractor.
try:                                    # noqa: SIM105  sibling, heavy-ish
    from final_assembler import frame_text as _FT
except Exception:                       # noqa: BLE001  module still works standalone
    _FT = None

_OCR_BASES = ((OnscreenTextError,) if _FT is None
              else (OnscreenTextError, _FT.FrameTextError))


class OCRUnavailable(*_OCR_BASES):
    """The words were never read; nothing may be called verified."""
    def __init__(self, message):
        OnscreenTextError.__init__(self, OCR_UNAVAILABLE, message)


# ------------------------------------------------------------------ text ----

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(text):
    """Comparison form of a word/phrase: case, punctuation and spacing never
    decide a spelling — a wrong LETTER still fails (that is the whole check)."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return _WS.sub(" ", _PUNCT.sub(" ", text.casefold())).strip()


def no_text_block():
    """The prompt block every Agnes picture carries by default (exact string)."""
    return NO_TEXT_BLOCK


def bake_block(text):
    """The prompt block for the one shot that must carry exactly these words.

    The exact string is quoted back into the prompt so the shot's expected
    text and the prompt's text can never drift apart.
    """
    if not isinstance(text, str) or not text.strip():
        raise OnscreenTextError(BAD_INPUT,
                                "bake_block needs the exact words to bake")
    words = text.strip()
    return ('The scene shows the written words "%s" and nothing else written. '
            'No other words, letters, numbers, logos, signage, captions or '
            'subtitles anywhere in the image.' % words)


# ------------------------------------------------------------------- ocr ----

def tesseract_bin():
    """Where the OCR binary is, or None: a caller may print "not installed"
    instead of running the read that would fail."""
    return shutil.which(ENGINE)


def read_still(path):
    """One still -> the words OCR ACTUALLY read (never the words we hoped for).

    Raises OCRUnavailable when the binary is missing or the read fails: a
    still nobody read is never a verified still.
    """
    exe = tesseract_bin()
    if not exe:
        raise OCRUnavailable("%s is not installed; a still cannot be verified, "
                             "so the words are overlaid instead of baked"
                             % ENGINE)
    try:
        proc = _LG.run_heavy([exe, str(path), "stdout", "--psm", str(PSM)],
                             job="%s-ocr" % ENGINE, capture_output=True,
                             text=True, errors="replace", timeout=120,
                             check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OCRUnavailable("%s could not run: %s" % (ENGINE, exc)) from exc
    if proc.returncode != 0:
        raise OCRUnavailable("%s exited %s: %s"
                             % (ENGINE, proc.returncode,
                                (proc.stderr or "").strip()[-200:]))
    return (proc.stdout or "").strip()


def tesseract_extractor(frame_paths):
    """frame_text extractor contract: one entry per frame.

    None = that frame carries no readable text. A frame that could not be
    read raises OCRUnavailable rather than being reported as clean.
    """
    out = []
    for path in frame_paths or []:
        out.append(read_still(path) or None)
    return out


REGISTERED = False                     # did the frame gate get the OCR extractor?

if _FT is not None:
    try:
        _FT.register_extractor(ENGINE, tesseract_extractor)
        REGISTERED = True
    except Exception:                  # noqa: BLE001  registration is advisory
        REGISTERED = False


# --------------------------------------------------------------- verify -----

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_still(path, expected, extractor=None):
    """Read one still back with OCR and compare it to the exact words.

    Returns a row: ``verdict`` PASS | FAIL | UNAVAILABLE with ``reason_code``,
    ``read`` (what OCR said), ``expected``, both normalized forms, ``sha256``
    of the still that was read and the ``engine`` that read it.

    PASS only on an exact match. Anything unreadable is UNAVAILABLE and is
    never a PASS — no engine, a crashed read, a missing file, an empty read.
    """
    if isinstance(path, (str, os.PathLike)) and str(path).strip():
        path = os.fspath(path)
    else:
        path = ""
    row = {"path": path, "expected": expected if isinstance(expected, str)
           else expected, "expected_norm": normalize(expected),
           "read": "", "read_norm": "", "sha256": None,
           "engine": ENGINE if extractor is None
                     else getattr(extractor, "__name__", "custom"),
           "verdict": VERDICT_UNAVAILABLE, "reason_code": None}

    if not isinstance(expected, str) or not row["expected_norm"]:
        row["reason_code"] = BAD_INPUT
        return row
    if not path or not os.path.isfile(path):
        row["reason_code"] = STILL_UNAVAILABLE
        return row
    row["sha256"] = _sha256(path)

    fn = tesseract_extractor if extractor is None else extractor
    try:
        got = fn([path])
    except OCRUnavailable as exc:            # fail closed, never a PASS
        row["reason_code"] = exc.code
        row["detail"] = str(exc)
        return row
    except Exception as exc:                 # noqa: BLE001  fail closed
        row["reason_code"] = OCR_FAILED
        row["detail"] = "extractor %s crashed: %s" % (row["engine"], exc)
        return row

    if not isinstance(got, list) or len(got) != 1:
        row["reason_code"] = OCR_FAILED
        row["detail"] = ("extractor %r returned %s for one still; must be "
                         "exactly one entry" % (row["engine"],
                                                type(got).__name__))
        return row

    read = got[0]
    row["read"] = "" if read is None else str(read)
    row["read_norm"] = normalize(row["read"])
    if row["read_norm"] == row["expected_norm"]:
        row["verdict"] = VERDICT_PASS
        return row
    row["verdict"] = VERDICT_FAIL
    row["reason_code"] = TEXT_NOT_VERIFIED
    return row


# --------------------------------------------------------------- decide -----

def _overlay_hook():
    """The decided fallback: the excerpt overlay draws the words at assembly."""
    try:
        from final_assembler.captions_burn import EXCERPT_OVERLAY_HOOK
        return EXCERPT_OVERLAY_HOOK
    except Exception:                  # noqa: BLE001  string below is the same hook
        return "final_assembler.captions_burn.overlay_excerpt"


def _shot_text(shot):
    """The exact words this shot needs, or None when it needs none."""
    if isinstance(shot, str):
        return shot.strip() or None
    if isinstance(shot, dict):
        for key in ("text", "on_screen_text"):
            value = shot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _verdict_of(try_row):
    if isinstance(try_row, str):
        return try_row.strip().upper()
    if isinstance(try_row, dict):
        return str(try_row.get("verdict", "")).strip().upper()
    return ""


def decide(shot, tries):
    """BAKED when a bake verified inside MAX_TRIES tries, else OVERLAY.

    ``shot`` is the shot/plan row (or its exact words); ``tries`` is the
    ``verify_still`` rows in attempt order (a bare verdict string is accepted
    too). Tries past ``MAX_TRIES`` are counted in the receipt and never used:
    the decided fallback after 3 misses is the overlay, not a fourth bake.

    Returns ``decision`` BAKED | OVERLAY, the receipt word (``TEXT_BAKED`` /
    ``TEXT_OVERLAID``), ``reason_code``, the rows, the hook the overlay draws
    with, and ``verified`` (True only on a real PASS read).
    """
    text = _shot_text(shot)
    if not text:
        raise OnscreenTextError(BAD_INPUT,
                                "decide() needs the shot's exact words")
    rows = list(tries or [])
    used = rows[:MAX_TRIES]

    for row in used:
        if _verdict_of(row) == VERDICT_PASS:
            return {"decision": "BAKED", "receipt": TEXT_BAKED,
                    "reason_code": None, "verified": True, "text": text,
                    "tries_used": len(used), "tries_total": len(rows),
                    "tries": rows, "overlay_hook": None}

    reason = TEXT_NOT_VERIFIED
    for row in used:
        if _verdict_of(row) == VERDICT_UNAVAILABLE:
            reason = OCR_UNAVAILABLE      # nobody read it: never a PASS
            break
    return {"decision": "OVERLAY", "receipt": TEXT_OVERLAID,
            "reason_code": reason, "verified": False, "text": text,
            "tries_used": len(used), "tries_total": len(rows),
            "tries": rows, "overlay_hook": _overlay_hook()}
