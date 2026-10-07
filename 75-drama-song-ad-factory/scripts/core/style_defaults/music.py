"""Music-style wiring for the D24 default (plan 4.1 Music line, D18).

No choice -> Soul Ballad. The vocabulary, the labels, the Suno style-field
prompt and the section hints belong to ``core/music_styles`` (unit
V2B-AUDIO-U2); this module only decides which one applies and fetches what
the music layer asks for. It never invents a prompt of its own.

stdlib only; no network, no runner, no spend, no file writes.
"""
from __future__ import annotations

from . import defaults as D


def music_style_ref(choice=None, source=None):
    """The resolved music style plus everything the music layer asks for.

    Returns the D24 row (``id`` / ``label`` / ``source`` / ``default_source``)
    with ``suno_prompt`` and ``section_hint`` read straight from
    ``core/music_styles``.
    """
    ref = D.resolve_music_style(choice, source)
    ms = D.MUSIC_STYLES
    ref["suno_prompt"] = ms.style_prompt(ref["id"])
    ref["section_hint"] = ms.section_hint(ref["id"])
    return ref
