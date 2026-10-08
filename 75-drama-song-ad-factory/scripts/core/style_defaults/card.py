"""The D24 defaults on the choice card (plan 4.1).

Exactly two lines carry a default marker::

    Style:       Lifelike 3D (default)  /  ... five looks ...
    Music:       Soul Ballad (default)  /  R&B Flow  /  Soul Rise

The Style line is rendered by ``choice_card.looks`` (that unit owns the five
looks) and composed here so both lines of the pair are produced in one place.
The Music line is owned here -- nothing else on the card offers a music
default marker. Applying the choices writes the two fields and nothing else.
"""
from __future__ import annotations

from . import defaults as D

STYLE_FIELD = D.STYLE_FIELD                 # "style"
MUSIC_FIELD = D.MUSIC_FIELD                 # "music"


def style_line():
    """Plan 4.1 Style line: five looks, the D24 default marked."""
    return D.LOOKS.style_line()


def music_line():
    """Plan 4.1 Music line: three styles, the D24 default marked."""
    parts = []
    for sid in D.MUSIC_STYLES.style_ids():
        label = D.MUSIC_STYLES.style(sid)["label"]
        if sid == D.DEFAULT_MUSIC_STYLE:
            label = "%s (default)" % label
        parts.append(label)
    return "  Music:       %s" % "  /  ".join(parts)


def choice_card_lines():
    """Both default-bearing lines, in card order (Style, then Music)."""
    return [style_line(), music_line()]


def apply_choices(card, style=None, music=None):
    """Copy of the card with the two style fields resolved. Nothing else.

    A field left off is not a blank: an already-recorded choice on the card is
    still a choice, so it is re-resolved as provided; only a genuinely absent
    value takes the D24 default. Length, shape, voice, clips, video model and
    price come back byte-identical and the caller's card is never mutated.
    """
    if not isinstance(card, dict):
        raise D.StyleDefaultsError("CARD_INVALID",
                                   "choice card must be a dict, got %s"
                                   % type(card).__name__)
    out = dict(card)
    if style is None:
        style = out.get(STYLE_FIELD)
    if music is None:
        music = out.get(MUSIC_FIELD)
    out[STYLE_FIELD] = D.resolve_style(style)["id"]
    out[MUSIC_FIELD] = D.resolve_music_style(music)["id"]
    return out
