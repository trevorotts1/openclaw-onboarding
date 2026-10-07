#!/usr/bin/env python3
"""Sketch to Life is always All Suno (owner D25; decision log 2026-10-07).

Source: Decision log 38 (D25 Sketch to Life) 2026-10-07; plan 6.12.1, 4.1.

The owner's order, verbatim::

    "When we use that hybrid and we go from the hand-drawn character to the
     realistic character, that's got to be all Suno."

Plan 6.12.1 says it the other way round: *Not available with the Sketch to
Life hybrid, which is always All Suno (owner 2026-10-07).*

The Voice line this unit renders is plan 4.1's own wording, D25 note included.
Two on-disk transcriptions of that line lack the note
(``core/docs_rename_velvet_voiceover/rename.py::VOICE_LINE`` and the
``references/choice-card-spec.md`` card block); both belong to other units and
are left untouched here -- see the lane receipt's ``label_drift`` note.

What this module owns and nothing else:

1. the **card Voice row for a chosen look** -- ``voice_options_for()`` /
   ``voice_line()`` / ``card_voice_block()`` hand the card the two voice
   options for four looks, and for ``sketch-to-life`` Velvet Voiceover comes
   back either **disabled** (default: still listed, ``selectable`` is False,
   with the unavailable note) or **hidden** (``mode="hide"``: dropped from the
   line entirely). All Suno stays the default on every look (Decision 27).
2. the **intake refusal** -- ``guard_intake(look, voice)`` returns
   ``outcome="refused"`` with a clear client-facing reason and a re-ask whose
   ``preselected`` payload is All Suno, so the client is never asked twice and
   never gets a silently swapped choice.
3. ``apply_voice()`` -- the copy-on-write guard for the card writer: writing
   Velvet Voiceover onto a Sketch to Life card raises ``StlGuardError``
   (code ``stl-voice-velvet-not-offered``) and leaves the caller's card alone.

Every other look -- Lifelike 3D, 2D Hand-Painted, Canvas to Life, Canvas to 3D
-- keeps Velvet Voiceover exactly as it was.

Look vocabulary comes from ``choice_card.looks`` and voice ids from
``voice_velvet_echo.velvet_voiceover``: neither is redefined here. The hyphen
slugs the card composer uses (``all-suno`` / ``velvet-voiceover``) and the
retired ``velvet_echo`` slug both normalize to the canonical ids before the
guard runs.

Wiring (three call sites, all done in this unit's run -- the refusal has to
be live on the real intake and the real card, not merely available):

* ``core/smp/initial_questions/initial_questions.py::resolve_style``, the
  planner's look/voice intake, calls ``guard_intake(style["look"],
  style["voice"])`` and, on ``outcome="refused"``, raises
  ``InitialQuestionsError(REASON_CODE, CLIENT_REASON)`` with the whole
  refusal dict attached as ``.reask`` -- the planner re-asks with All Suno
  pre-selected instead of storing the pair.
* ``core/batch_mode/batch.py::make_card`` raises ``BatchError(REASON_CODE,
  CLIENT_REASON)`` so the pair never reaches a card, and
  ``batch.py::card_lines`` prints All Suno for a card that already carries
  the pair (loaded from disk), so no card ever shows Velvet Voiceover on
  Sketch to Life.
* The single-ad card's Voice row is this module's: ``voice_line(look)`` /
  ``voice_options_for(look)`` / ``card_voice_block(look, selected)`` stand
  in for the look-less ``voice_velvet_echo.voice_line()``.

stdlib only. No network module, no provider call, no spend, no media file,
no absolute operator path (the workspace root is found by walking up from this
file). Media generation stays on Skill 74's KIE path -- this module never
reaches it.

Run: python3 core/choice_card/stl_voice_guard/test_stl_voice_guard.py
"""
from __future__ import annotations

import os
import re
import sys

_CORE = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:
    from choice_card import looks as LOOKS
except ImportError as _e:                      # imported as core.choice_card
    if "choice_card" not in str(_e):
        raise
    from .. import looks as LOOKS              # type: ignore

try:
    from voice_velvet_echo import velvet_voiceover as VV
except ImportError as _e:
    if "voice_velvet_echo" not in str(_e):
        raise
    raise ImportError(
        "stl_voice_guard needs the sibling package voice_velvet_echo in %s"
        % (_CORE,)
    ) from _e

TOOL_NAME = "choice_card.stl_voice_guard"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.choice-card/stl-voice-guard/v1"
SOURCE = "Decision log 38 (D25 Sketch to Life) 2026-10-07; plan 6.12.1, 4.1"

# ---- the one look this guard is about -------------------------------------
STL_LOOK_ID = "sketch-to-life"
STL_LOOK_LABEL = "Sketch to Life"

#: The other four keeps. LOOK_ORDER is the card's own five-look menu.
STL_OTHER_LOOKS = tuple(lid for lid in LOOKS.LOOK_ORDER if lid != STL_LOOK_ID)

# ---- voice ids come from the Velvet module; never redefined here -----------
ALL_SUNO_ID = VV.ALL_SUNO_ID
VELVET_ID = VV.VELVET_ID
DEFAULT_VOICE_ID = VV.DEFAULT_VOICE_ID
LEGACY_VOICE_IDS = VV.LEGACY_VELVET_IDS
VoiceError = VV.VelvetError

#: Card composer spellings (hyphen slugs) -> canonical underscore ids.
_SLUG_ALIASES = {
    "all-suno": ALL_SUNO_ID,
    "velvet-voiceover": VELVET_ID,
    "velvet-echo": VELVET_ID,
}

VOICE_FIELD = "voice"                          # card field key (batch CARD_FIELDS)
VOICE_LINE_PREFIX = VV.VOICE_LINE_PREFIX

#: Plan 4.1 column: the label plus padding puts the body at column 13.
_CARD_SPACING = " " * (13 - len(VOICE_LINE_PREFIX))

#: The sibling package's label as it ships today (no D25 note) -- kept only so
#: that spelling still resolves; never rendered on a card from here.
VV_LABEL_NO_NOTE = next(o["label"] for o in VV.voice_options()
                        if o["id"] == VELVET_ID)

#: Plan 4.1 prints the option exactly like this -- the D25 note rides inside
#: the label on every card, so the client reads the constraint before picking.
#: The sibling ``voice_velvet_echo`` label (same words, no note) is still
#: registered as an accepted intake spelling below, so nothing carrying the
#: pre-D25 wording breaks.
ALL_SUNO_LABEL = "All Suno (default)"
VELVET_LABEL = (
    "Velvet Voiceover (Google voiceover with the song underneath; "
    "not with Sketch to Life)"
)
#: How the disabled option reads on a Sketch to Life card (mode="disable").
VELVET_DISABLED_LABEL = "Velvet Voiceover (unavailable with Sketch to Life)"

#: "disable" keeps the row and marks the option; "hide" drops it from the line.
MODES = ("disable", "hide")
DEFAULT_MODE = "disable"

# ---- client-facing wording ------------------------------------------------
REASON_CODE = "stl-voice-velvet-not-offered"

CLIENT_REASON = (
    "Sketch to Life always uses All Suno. On this look the hand-drawn "
    "character changes into the realistic character to the Suno song, so "
    "Velvet Voiceover (the Google voiceover) is not offered with it. "
    "Continue with All Suno, or choose a different look."
)

REASK_QUESTION = (
    "Velvet Voiceover is not available with Sketch to Life. All Suno is "
    "already pre-selected -- continue with All Suno, or choose a different "
    "look?"
)

REASK_ID = "voice"
NEXT_ACTION_OK = "Continue to the choice card."
NEXT_ACTION_REFUSED = "Re-present the card with All Suno pre-selected."


class StlGuardError(Exception):
    """A refusal this guard owns: bad look, bad voice, forbidden pairing."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# ---------------------------------------------------------------- look -----
def resolve_look(look=None):
    """Look id via the card's own five-look menu; a refusal becomes ours."""
    try:
        return LOOKS.resolve_look(look)
    except Exception as exc:                    # noqa: BLE001
        raise StlGuardError(getattr(exc, "code", "LOOK_NOT_OFFERED"),
                            str(exc)) from exc


def velvet_offered_with(look=None):
    """True: Velvet Voiceover is on offer for this look (false only for STL)."""
    return resolve_look(look) != STL_LOOK_ID


def is_forbidden(look, voice):
    """True only for the one forbidden pair: Sketch to Life + Velvet Voiceover."""
    return (resolve_look(look) == STL_LOOK_ID
            and _resolve_voice(voice) == VELVET_ID)


# --------------------------------------------------------------- voice -----
def _norm(text):
    """Case/separator-insensitive normal form, so the card's labels resolve."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


#: Every spelling that still means one of the two voice ids: the ids
#: themselves, the card composer's hyphen slugs, the retired slug, and every
#: label the card or the plan prints (including the parenthetical notes).
_VOICE_BY_NORM = {}
for _opt in VV.voice_options():
    _VOICE_BY_NORM[_norm(_opt["id"])] = _opt["id"]
    _VOICE_BY_NORM[_norm(_opt["label"])] = _opt["id"]
    _VOICE_BY_NORM[_norm(_opt["label"].split(" (")[0])] = _opt["id"]
for _slug, _canon in _SLUG_ALIASES.items():
    _VOICE_BY_NORM[_norm(_slug)] = _canon
for _legacy in LEGACY_VOICE_IDS:
    _VOICE_BY_NORM[_norm(_legacy)] = VELVET_ID
_VOICE_BY_NORM[_norm(ALL_SUNO_LABEL)] = ALL_SUNO_ID
_VOICE_BY_NORM[_norm(VELVET_LABEL)] = VELVET_ID
#: The sibling package ships the same label without the D25 note -- that
#: spelling must keep resolving, so old callers do not break.
_VOICE_BY_NORM[_norm(VV_LABEL_NO_NOTE)] = VELVET_ID
_VOICE_BY_NORM[_norm(VELVET_DISABLED_LABEL)] = VELVET_ID

#: Prefixes that carry a parenthetical note the card appends (plan 4.1).
_PREFIX_FALLBACK = (
    ("velvetvoiceover", VELVET_ID),
    ("velvetecho", VELVET_ID),
    ("allsuno", ALL_SUNO_ID),
)


def _resolve_voice(voice=None):
    """Canonical voice id; slugs, labels and the retired slug all normalize.

    An unknown choice fails closed by name -- the guard never guesses a voice
    the client did not pick.
    """
    if voice is None:
        return DEFAULT_VOICE_ID
    if not isinstance(voice, str):
        raise StlGuardError("VOICE_NOT_OFFERED",
                            "voice choice must be a string, got %r" % (voice,))
    norm = _norm(voice)
    if not norm:
        return DEFAULT_VOICE_ID
    hit = _VOICE_BY_NORM.get(norm)
    if hit is None:
        for prefix, canonical in _PREFIX_FALLBACK:
            if norm.startswith(prefix):
                hit = canonical
                break
    if hit is None:
        raise StlGuardError(
            "VOICE_NOT_OFFERED",
            "voice choice %r is not one of %s"
            % (voice, sorted({o["id"] for o in VV.voice_options()})))
    return hit


def normalize_voice_choice(voice=None):
    """Public alias of the canonical voice-id resolver."""
    return _resolve_voice(voice)


def selectable_voice_ids(look=None):
    """The voice ids a client may actually pick for this look, in card order."""
    lid = resolve_look(look)
    if lid == STL_LOOK_ID:
        return (ALL_SUNO_ID,)
    return tuple(_resolve_voice(opt["id"]) for opt in VV.voice_options())


def voice_options_for(look=None, mode=DEFAULT_MODE):
    """The Voice row's options for this look, each flagged selectable or not.

    mode="disable" (default) lists Velvet Voiceover with ``selectable=False``
    and the unavailable label; mode="hide" leaves it out altogether. Every
    other look returns both options selectable.
    """
    if mode not in MODES:
        raise StlGuardError("MODE_UNKNOWN",
                            "mode %r is not one of %s" % (mode, ", ".join(MODES)))
    lid = resolve_look(look)
    offered = lid != STL_LOOK_ID
    options = [
        {"id": ALL_SUNO_ID,
         "label": ALL_SUNO_LABEL,
         "engine": "suno",
         "default": True,
         "google": False,
         "selectable": True,
         "hidden": False,
         "unavailable_reason": None},
    ]
    if offered:
        options.append({"id": VELVET_ID,
                        "label": VELVET_LABEL,
                        "engine": "google_tts",
                        "default": False,
                        "google": True,
                        "selectable": True,
                        "hidden": False,
                        "unavailable_reason": None})
    elif mode == "disable":
        options.append({"id": VELVET_ID,
                        "label": VELVET_DISABLED_LABEL,
                        "engine": "google_tts",
                        "default": False,
                        "google": True,
                        "selectable": False,
                        "hidden": False,
                        "unavailable_reason": CLIENT_REASON})
    return options


def voice_line(look=None, mode=DEFAULT_MODE):
    """The card's Voice line for this look (plan 4.1 column alignment)."""
    options = voice_options_for(look, mode)
    labels = [opt["label"] for opt in options if not opt["hidden"]]
    return "%s%s%s" % (VOICE_LINE_PREFIX, _CARD_SPACING, "  /  ".join(labels))


def card_voice_block(look=None, selected=None, mode=DEFAULT_MODE):
    """Machine-readable Voice field for the card, for one look.

    ``selected`` that the look forbids is reported back as All Suno with
    ``forced=True`` and ``rejected`` naming what was refused -- that is the
    "All Suno pre-selected" the re-ask carries.
    """
    lid = resolve_look(look)
    choice = _resolve_voice(selected)
    options = voice_options_for(lid, mode)
    selectable = tuple(o["id"] for o in options if o["selectable"])
    forced = choice not in selectable
    if forced:
        choice = ALL_SUNO_ID
    for opt in options:
        opt["selected"] = opt["id"] == choice
    return {
        "schema_version": SCHEMA_VERSION,
        "field": "Voice",
        "line": voice_line(lid, mode),
        "look": lid,
        "options": options,
        "selectable": list(selectable),
        "selected": choice,
        "default": DEFAULT_VOICE_ID,
        "forced": forced,
        "rejected": (_resolve_voice(selected) if forced else None),
        "reason": (CLIENT_REASON if forced else None),
        "option_count": len(options),
    }


# -------------------------------------------------------------- intake -----
def guard_intake(look=None, voice=None):
    """Intake gate: refuse the forbidden pair, re-ask with All Suno selected.

    Returns an intake-shaped dict. ``outcome="refused"`` carries the clear
    client-facing reason, the re-ask question and its ``preselected`` payload
    (All Suno on the same look). ``outcome="ok"`` means the pair is on offer.
    Unknown look or unknown voice raises ``StlGuardError`` -- the guard never
    guesses a choice the client did not make.
    """
    lid = resolve_look(look)
    vid = _resolve_voice(voice)
    if vid in selectable_voice_ids(lid):        # STL offers All Suno only
        return {
            "outcome": "ok",
            "reason_code": "stl-voice-guard-pass",
            "look": lid,
            "voice": vid,
            "questions": [],
            "question_message": None,
            "preselected": None,
            "client_message": None,
            "next_action": NEXT_ACTION_OK,
        }
    return {
        "outcome": "refused",
        "reason_code": REASON_CODE,
        "look": lid,
        "voice": ALL_SUNO_ID,
        "rejected_voice": vid,
        "questions": [{
            "id": REASK_ID,
            "question": REASK_QUESTION,
            "preselected": {"look": lid, "voice": ALL_SUNO_ID},
            "selectable": list(selectable_voice_ids(lid)),
        }],
        "question_message": REASK_QUESTION,
        "preselected": {"look": lid, "voice": ALL_SUNO_ID},
        "client_message": CLIENT_REASON,
        "next_action": NEXT_ACTION_REFUSED,
    }


def guard(look=None, voice=None, mode=DEFAULT_MODE):
    """Alias of ``guard_intake`` for card-side callers.

    ``mode`` is accepted and ignored: how the card draws the row never changes
    whether the pair is allowed.
    """
    return guard_intake(look, voice)


# ----------------------------------------------------------- card write ----
def apply_voice(card, look=None, voice=None, mode=DEFAULT_MODE):
    """Copy of the card with only the voice field written -- or a refusal.

    Same contract as ``choice_card.looks.apply_look``: the caller's card is
    never mutated and every other field comes back byte-identical. Sketch to
    Life + Velvet Voiceover raises ``StlGuardError`` instead of writing.
    """
    if not isinstance(card, dict):
        raise StlGuardError("CARD_INVALID", "choice card must be a dict")
    lid = resolve_look(look if look is not None else card.get("style"))
    vid = _resolve_voice(voice)
    if lid == STL_LOOK_ID and vid == VELVET_ID:
        raise StlGuardError(REASON_CODE, CLIENT_REASON)
    out = dict(card)
    out[VOICE_FIELD] = vid
    return out


def build_root():
    """The workspace that owns core/, found by walking up from this file."""
    path = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(path, "core", "choice_card")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
