"""Style defaults D24 (owner decision, 2026-10-07): the client who does not
choose gets **Lifelike 3D + Soul Ballad**.

This module owns the D24 policy and nothing else -- which value applies when
nobody chose, what an explicit choice does to it, and the provenance the card
can print. The vocabularies stay where they already were:

* visual look ids and their Style Bible records -> ``core/choice_card/looks``
* music style ids, labels and Suno prompts      -> ``core/music_styles``
* Style Bible compile + consumption gate        -> ``core/style_bible_integration``

Nothing here opens a socket, spawns a runner, spends money or writes a file.
stdlib only.
"""
from __future__ import annotations

import re

#: Look vocabulary + Style Bible records (D21 five-look card).
try:
    from choice_card import looks as LOOKS
except ImportError as _e:                      # imported as core.style_defaults
    if "choice_card" not in str(_e):
        raise
    from ..choice_card import looks as LOOKS    # type: ignore

#: Music vocabulary + Suno prompts (D18 three styles).
try:
    import music_styles as MUSIC_STYLES
except ImportError as _e:                      # imported as core.style_defaults
    if "music_styles" not in str(_e):
        raise
    from .. import music_styles as MUSIC_STYLES  # type: ignore

#: The D24 pair, exactly as the owner wrote it.
DEFAULT_STYLE = "lifelike-3d"
DEFAULT_MUSIC_STYLE = "soul-ballad"

#: Decision-log stamp the card prints so the default stays attributable.
SOURCE_OF_DEFAULT = "Owner D24 2026-10-07"

#: The card writes the look under LOOK_FIELD ("style") and the music under
#: "music"; both names are read back by apply_choices.
STYLE_FIELD = "style"
MUSIC_FIELD = "music"

#: What the client typed that still means "no choice": the card's own
#: "(default)" marker, and the plain refusal spellings.
_TRAILING_DEFAULT_RE = re.compile(r"\s*\(\s*(?:the\s+)?default\s*\)", re.I)
_NO_CHOICE = frozenset(("", "default", "none", "nochoice", "no choice"))


class StyleDefaultsError(Exception):
    """A refusal this policy owns: bad choice, unknown choice, no vocabulary."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _norm(text):
    """Case/separator-insensitive normal form, for echoing the card back."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _clean(choice):
    """-> ``(value, marked_default)``; value is None when nobody chose.

    None, empty, whitespace and the plain refusal spellings all mean "the
    client did not choose". The card prints its D24 default as
    ``Lifelike 3D (default)`` / ``Soul Ballad (default)``, so a submitted
    label carrying that marker is a no-choice answer too -- ``marked_default``
    says so while still returning the label for the echo check. Anything else
    must be a string: a bool or an int is a caller bug, not a default.
    """
    if isinstance(choice, dict):            # card option block {"value": ...}
        choice = choice.get("value",
                            choice.get(STYLE_FIELD,
                                       choice.get(MUSIC_FIELD, choice.get("id"))))
    if choice is None:
        return None, False
    if not isinstance(choice, str):
        raise StyleDefaultsError(
            "BAD_CHOICE", "style/music choice must be a string, got %s"
            % type(choice).__name__)
    text = choice.strip()
    marked = bool(_TRAILING_DEFAULT_RE.search(text))
    value = _TRAILING_DEFAULT_RE.sub("", text).strip()
    if re.sub(r"[\s_-]+", " ", value.lower()) in _NO_CHOICE:
        return None, marked
    return value, marked


def _row(sid, label, source):
    return {
        "id": sid,
        "label": label,
        "source": source,                   # "default" | "provided"
        "default_source": SOURCE_OF_DEFAULT,
    }


def style_label(style_id):
    """Card label for a look id (unknown id comes back unchanged)."""
    return LOOKS.LOOK_LABELS.get(style_id, style_id)


def music_label(music_id):
    """Card label for a music style id (unknown id comes back unchanged)."""
    return MUSIC_STYLES.style(music_id).get("label", music_id)


def resolve_style(choice=None, source=None):
    """Visual look. No choice -> lifelike-3d; an explicit choice wins.

    The look vocabulary and its refusals belong to ``choice_card.looks``;
    this only decides whether the D24 default applies. An off-menu look is
    refused by name -- never silently defaulted.
    """
    value, marked = _clean(choice)
    if value is None or (marked and _norm(value) in (
            _norm(DEFAULT_STYLE), _norm(style_label(DEFAULT_STYLE)))):
        return _row(DEFAULT_STYLE, style_label(DEFAULT_STYLE), "default")
    try:
        sid = LOOKS.resolve_look(value)
    except Exception as exc:                # noqa: BLE001 - wrap the refusal
        raise StyleDefaultsError(
            "UNKNOWN_STYLE", "%r is not an offered look: %s" % (value, exc)
        ) from exc
    return _row(sid, style_label(sid), source or "provided")


def resolve_music_style(choice=None, source=None):
    """Music style. No choice -> soul-ballad; an explicit choice wins.

    The vocabulary, its labels and its refusals belong to
    ``core/music_styles`` (unit V2B-AUDIO-U2).
    """
    value, marked = _clean(choice)
    if value is None or (marked and _norm(value) in (
            _norm(DEFAULT_MUSIC_STYLE),
            _norm(music_label(DEFAULT_MUSIC_STYLE)))):
        return _row(DEFAULT_MUSIC_STYLE,
                    music_label(DEFAULT_MUSIC_STYLE), "default")
    try:
        sid = MUSIC_STYLES.style(value)["style_id"]
    except Exception as exc:                # noqa: BLE001 - wrap the refusal
        raise StyleDefaultsError(
            "UNKNOWN_MUSIC_STYLE",
            "%r is not one of the three D18 styles: %s" % (value, exc)
        ) from exc
    return _row(sid, music_label(sid), source or "provided")


def default_pair():
    """The D24 pair, exactly as the owner wrote it."""
    return {
        "style": DEFAULT_STYLE,
        "style_label": style_label(DEFAULT_STYLE),
        "music_style": DEFAULT_MUSIC_STYLE,
        "music_style_label": music_label(DEFAULT_MUSIC_STYLE),
        "source": SOURCE_OF_DEFAULT,
    }
