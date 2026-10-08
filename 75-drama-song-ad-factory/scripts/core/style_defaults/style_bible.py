"""Style Bible injection for the D24 default look (D13 / plan 6.11).

D13: "the choice swaps the Style Bible block injected into every visual
prompt". With no choice that block is Lifelike 3D, not the 2D record
``style_bible_integration`` reaches for when ``style=None``.

Ownership split, unchanged:

* look -> Style Bible record map and the ``[STYLE]...[/STYLE]`` renderer
  live in ``core/choice_card/looks``;
* the compiler and the consumption gate live in
  ``core/style_bible_integration``;
* this module only decides WHICH look applies and hands it over.

stdlib only; no network, no runner, no spend, no file writes.
"""
from __future__ import annotations

import copy

from . import defaults as D

try:
    from style_bible_integration import compile_visual as _gate_compile
except ImportError as _e:                      # imported as core.style_defaults
    if "style_bible_integration" not in str(_e):
        raise
    from ..style_bible_integration import compile_visual as _gate_compile  # type: ignore


def _look_record(look=None):
    """Deep copy of the Style Bible record for the resolved look."""
    sid = D.resolve_style(look)["id"]
    # The record map lives in the package's implementation module; the
    # package re-exports only the block renderer.
    # ponytail: reach for a public choice_card.looks.style_record(look) once
    # that unit publishes one, then delete this getattr chain.
    impl = getattr(D.LOOKS, "looks", D.LOOKS)
    records = getattr(impl, "_RECORDS", None) or {}
    rec = records.get(sid)
    if rec is None and sid == D.DEFAULT_STYLE:
        rec = getattr(impl, "LIFELIKE_3D_STYLE", None)
    if rec is None:
        raise D.StyleDefaultsError("NO_STYLE_RECORD",
                                   "no Style Bible record for look %r" % sid)
    return copy.deepcopy(rec)


def style_record(look=None, aspect_ratio=None):
    """The record to hand ``style_bible_integration.compile_visual``."""
    rec = _look_record(look)
    if aspect_ratio is not None:
        rec["aspect_ratio"] = aspect_ratio
    return rec


def style_bible_block(look=None, aspect_ratio=None):
    """``[STYLE]...[/STYLE]`` for the resolved look; no choice -> Lifelike 3D."""
    sid = D.resolve_style(look)["id"]
    return D.LOOKS.bible_block(sid, aspect_ratio)


def inject_style_block(prompt, look=None, aspect_ratio=None):
    """Put the resolved look's Style Bible block into ``prompt``.

    No choice -> the Lifelike 3D block. An existing block is replaced in
    place (first one only); everything outside the block comes back
    byte-for-byte.
    """
    sid = D.resolve_style(look)["id"]
    return D.LOOKS.inject_style_block(prompt, sid, aspect_ratio)


def compile_visual(base_prompt, characters, product, shot, look=None,
                   aspect_ratio=None):
    """Compile through the Style Bible gate with the resolved look.

    This is the D24 half of the injection: ``style_bible_integration``'s own
    ``style=None`` default is the 2D resilia record, so leaving it unset would
    silently render the wrong look for a client who never chose.
    """
    return _gate_compile(base_prompt, characters, product, shot,
                         style=style_record(look, aspect_ratio),
                         aspect_ratio=aspect_ratio)
