"""presentation_job/vocab.py -- THE single source of truth for the engine's
`presentation_type` vocabulary.

fix/deck-type-routing-bypass
-----------------------------
Every caller that hands a deck type to the engine -- presentation-canonical-
entry.sh (the door), presentation_job/__main__.py (the engine itself),
presentation-intake-poll.sh (the poll), and presentation_job/launcher.py (the
launcher) -- MUST resolve it through normalize_presentation_type() below.

Before this fix there were TWO independently hand-maintained "legal" sets:
the engine's ("from_scratch", "content_personal", "content_general",
"signature") and the entry script's inline python copy, which additionally
listed "standard" and "signature_presentation" as members of its OWN "legal"
set -- so its alias-remap step never fired for exactly the two values that
needed it. A "signature_presentation" or "standard" intake sailed past the
entry script's check, hit the engine's real (narrower) legal tuple, got
rejected, and the door silently fell back to the 2-of-36-phase legacy
runner while reporting success. The poll script had no normalization at all
and defaulted the same way. Two hardcoded sets that can drift out of
agreement IS the bug; this module is the fix -- there is now exactly one.

CANONICAL_PRESENTATION_TYPES is the engine's `intake.presentation_type`
vocabulary (mirrors deck-intake-driver.py:LEGAL_PRESENTATION_TYPES, the
human-facing intake schema's own source of truth for this axis).

PRESENTATION_TYPE_ALIASES maps values seen from OTHER layers of the stack
onto exactly one canonical value:
  - "signature_presentation" is the SOP-governed `deck_type` field's name
    for what the engine calls presentation_type "signature" (see
    sops/SOP-SIGPRES-00-THE-SIGNATURE-PRESENTATION-LAW.md); a hand-rolled or
    legacy ledger can carry this value where the engine wants "signature".
  - "standard" is a plain-English label some intake surfaces have used for
    the default from_scratch deck.

An input that is neither canonical nor a known alias is NEVER silently
downgraded to a default. normalize_presentation_type() raises
UnknownPresentationType; every caller MUST treat that as a loud, blocking
failure -- never a caught-and-defaulted "from_scratch". Add new synonyms to
PRESENTATION_TYPE_ALIASES ONLY -- never inline in a caller, and never widen
CANONICAL_PRESENTATION_TYPES itself to swallow an alias.
"""
from __future__ import annotations

import sys
from typing import Optional

# The engine's legal presentation_type values (presentation_job/__main__.py
# cmd_new accepts exactly these -- see EXIT_USAGE die() there).
CANONICAL_PRESENTATION_TYPES = (
    "from_scratch",
    "content_personal",
    "content_general",
    "signature",
)

# Known synonyms from other layers of the stack, mapped onto exactly one
# canonical value above. Every key here must map to a value in
# CANONICAL_PRESENTATION_TYPES.
PRESENTATION_TYPE_ALIASES = {
    "standard": "from_scratch",
    "signature_presentation": "signature",
}

assert set(PRESENTATION_TYPE_ALIASES.values()) <= set(CANONICAL_PRESENTATION_TYPES), (
    "PRESENTATION_TYPE_ALIASES must map only onto CANONICAL_PRESENTATION_TYPES"
)
assert not (set(PRESENTATION_TYPE_ALIASES) & set(CANONICAL_PRESENTATION_TYPES)), (
    "an alias key must never also be a canonical value -- that is exactly the "
    "shape of the bug this module fixes (a value present in BOTH sets makes "
    "the alias remap unreachable)"
)


class UnknownPresentationType(ValueError):
    """Raised by normalize_presentation_type() for a value that is neither
    canonical nor a known alias. Callers MUST treat this as a loud, blocking
    failure -- catching it to fall back to a default silently reproduces the
    exact bug this module exists to close."""


def normalize_presentation_type(raw: Optional[str]) -> str:
    """Resolve `raw` to exactly one of CANONICAL_PRESENTATION_TYPES.

    Returns the canonical value on a match (identity or alias). Raises
    UnknownPresentationType on anything else, including None/empty -- there
    is no default here. A caller that wants a fallback must decide that
    explicitly and announce it; this function will never do it silently.
    """
    val = str(raw).strip() if raw is not None else ""
    if val in CANONICAL_PRESENTATION_TYPES:
        return val
    if val in PRESENTATION_TYPE_ALIASES:
        return PRESENTATION_TYPE_ALIASES[val]
    raise UnknownPresentationType(
        f"{raw!r} is not a legal presentation_type. Must be one of "
        f"{CANONICAL_PRESENTATION_TYPES} or a known alias of "
        f"{tuple(PRESENTATION_TYPE_ALIASES)}."
    )


def _cli(argv: Optional[list] = None) -> int:
    """`python3 -m presentation_job.vocab <raw-value>` -- prints the
    normalized value on stdout and exits 0, or prints AF-DECK-TYPE-UNKNOWN
    to stderr and exits 3. Lets shell callers resolve a value passed as a
    single argv element (never string-interpolated into python source, so a
    client-controlled string containing a quote or any other shell/python
    metacharacter is inert here)."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python3 -m presentation_job.vocab <raw-presentation-type>",
              file=sys.stderr)
        return 2
    try:
        print(normalize_presentation_type(args[0]))
        return 0
    except UnknownPresentationType as exc:
        print(f"AF-DECK-TYPE-UNKNOWN: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(_cli())
