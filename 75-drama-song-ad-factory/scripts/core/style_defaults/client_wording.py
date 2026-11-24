"""Client wording: what each look is called, and what clients say (N-36, section 3B.5).

Two things live here and nothing else:

* ``WHAT_CLIENTS_SAY`` -- the one mapping from a client's plain words to a look
  id. "Pixar", "Disney-style", "animated movie" and "cartoon 3D" mean Stylized 3D;
  "real", "real people" and "like a movie with actors" mean Realism; "Lifelike 3D"
  alone stays Lifelike 3D. Anything that matches two looks, or none, is ``None``:
  one question with the samples, never a guess.
* the guide-drift guard -- every mode file carries a ``client_wording`` line, and
  the guide's line for that look must equal it. ``check_guide_wording`` fails with
  ``CLIENT_WORDING_DRIFT`` when they differ, and ``check_guide_file`` reads
  ``references/CLIENT-GUIDE.md`` itself and runs that check on its bullet for the
  look, so the guide and the mode file can never drift again.

stdlib only: no network, no runner, no paid call, no file writes.
"""
from __future__ import annotations

import re

from .defaults import StyleDefaultsError
from .mode_files import load_mode

#: Ordered phrase -> look-id table. Phrases are matched whole (word boundaries)
#: and case-insensitively; distinct matches are collected and only a single
#: distinct look is returned.
WHAT_CLIENTS_SAY = (
    ("stylized-3d", ("pixar", "disney-style", "disney style", "animated movie",
                     "cartoon 3d", "cartoon 3-d")),
    ("realism", ("real people", "like a movie with actors", "real human being",
                 "real person", "real")),
    ("lifelike-3d", ("lifelike 3d", "lifelike")),
)


def _hits(text, phrases):
    low = str(text).lower()
    for phrase in phrases:
        pat = r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(phrase.lower())
        if re.search(pat, low):
            return True
    return False


def map_client_wording(text):
    """The one look id a client's words mean, or ``None`` when unclear.

    ``None`` means: ask one question with the samples. It is never a guess.
    Returns ``None`` for empty input too.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    matched = [look for look, phrases in WHAT_CLIENTS_SAY if _hits(text, phrases)]
    return matched[0] if len(matched) == 1 else None


def _norm(line):
    return re.sub(r"\s+", " ", str(line)).strip().casefold()


def client_wording_for(mode_id, root=None):
    """The ``client_wording`` line of a mode file (fails at load if missing)."""
    return load_mode(mode_id, root=root)["client_wording"]


_BULLET = re.compile(r"^\s*-\s+\*\*(?P<label>[^*]+?)\.\*\*\s*(?P<line>.+)$",
                     re.MULTILINE)


def guide_line_for(mode_id, guide_text, label=None, root=None):
    """The guide bullet's own words for one look, or ``None`` when it has none.

    The guide carries one bullet per look: ``- **Label.** <client wording>.
    Sample...``. Everything between the bold label and the ``Sample`` marker is
    that look's line. A bullet label may be shorter than the mode's own label
    ("Lifelike 3D" for "Lifelike 3D (cinematic CGI)"), so a prefix match is
    accepted; ``label`` overrides when a caller knows the exact card wording.
    """
    mode = load_mode(mode_id, root=root)
    wanted = [s.strip().casefold() for s in
              (label, mode.get("label"), mode_id) if s]
    for match in _BULLET.finditer(guide_text or ""):
        got = match.group("label").strip().casefold()
        if any(w == got or w.startswith(got) for w in wanted):
            return re.split(r"\s+Sample\b", match.group("line"),
                            maxsplit=1)[0].strip()
    return None


def check_guide_file(mode_id, guide_path, label=None, root=None):
    """The document guard: the guide's line for a look must equal its mode file.

    Reads the guide itself, so drift between ``references/CLIENT-GUIDE.md`` and
    a mode file's ``client_wording`` fails with ``CLIENT_WORDING_DRIFT``. A
    look with no bullet in the guide fails ``GUIDE_LINE_MISSING`` rather than
    passing unguarded.
    """
    try:
        with open(guide_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise StyleDefaultsError(
            "GUIDE_UNREADABLE", "%s (%s)" % (guide_path, exc)) from exc
    line = guide_line_for(mode_id, text, label=label, root=root)
    if line is None:
        raise StyleDefaultsError(
            "GUIDE_LINE_MISSING",
            "the guide at %s has no bullet for look %r" % (guide_path, mode_id))
    return check_guide_wording(mode_id, line, root=root)


def check_guide_wording(mode_id, guide_line, root=None):
    """Fail ``CLIENT_WORDING_DRIFT`` when the guide's line differs from the mode.

    Whitespace and letter case are ignored; the words must match. Returns the
    matched line so a caller can reuse it.
    """
    expected = client_wording_for(mode_id, root=root)
    if _norm(guide_line) != _norm(expected):
        raise StyleDefaultsError(
            "CLIENT_WORDING_DRIFT",
            "guide line for look %r does not match its mode file.\n"
            "  mode:  %s\n  guide: %s" % (mode_id, expected, guide_line))
    return guide_line


__all__ = [
    "WHAT_CLIENTS_SAY",
    "check_guide_file",
    "check_guide_wording",
    "client_wording_for",
    "guide_line_for",
    "map_client_wording",
]
