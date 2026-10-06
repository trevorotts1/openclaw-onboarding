#!/usr/bin/env python3
"""PRD 1.8 shim (PRES-053 packaged closure) — re-exports the canonical engine.

PRD 1.8 pins GEMINI_MODEL in exactly one file
(shared-utils/embedding_engine.py). This packaged copy used to be a second
full copy of that implementation, which defines GEMINI_MODEL twice and rots
(the two copies can only agree by accident). This module defines no model
constant; it locates the canonical engine (repo checkout, then installed
skills roots) and re-exports its public surface, so a GA model bump
propagates here automatically.

Loaded by path under the basename ``embedding_engine`` by PersonaService
(_preload_pinned_helpers + _load), exactly as before, so vendored consumers
(``from embedding_engine import GEMINI_MODEL ...``) are unaffected.
"""

import importlib.util as _ilu
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))

_CANDIDATES = [
    # Repo checkout: helpers/ is nine levels below the repo root.
    _os.path.normpath(_os.path.join(
        _HERE, *([_os.pardir] * 9), "shared-utils", "embedding_engine.py")),
    # Installed skills roots (client boxes: install.sh copies shared-utils
    # to the skills root).
    _os.path.expanduser("~/.openclaw/skills/shared-utils/embedding_engine.py"),
    "/data/.openclaw/skills/shared-utils/embedding_engine.py",
]

_FOUND = next(
    (_os.path.realpath(p) for p in _CANDIDATES if _os.path.isfile(p)), None)
if _FOUND is None:
    raise ImportError(
        "PRD 1.8 shim: canonical shared-utils/embedding_engine.py not found "
        "in %r" % (_CANDIDATES,))

_spec = _ilu.spec_from_file_location(
    "persona_service_canonical_embedding_engine", _FOUND)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def __getattr__(name):
    return getattr(_mod, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_mod)))
