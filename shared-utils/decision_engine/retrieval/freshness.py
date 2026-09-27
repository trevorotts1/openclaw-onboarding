#!/usr/bin/env python3
"""Stale persona-index detection (unit REP-032, JEV spec 1.1 ss 9.3 / A32).

The vector-space gate (``cache_identity``) can only see what an index DECLARES.
An index rebuilt from an older persona set, then read after the set moved on,
declares exactly the same space and is served as if current — probe case 6b.
This module closes that hole: it compares the index's own build stamp against
the live canonical persona set and answers fresh / stale / unknown, plus which
path may be served.

Stdlib only. Reads caller-supplied paths, writes nothing, calls nothing.

Contract:
  * Absent or unparseable stamp == fresh. Legacy/adopting boxes carry no
    stamp; that is a packaging state, not evidence of staleness, and refusing
    there would keyword-degrade every box on upgrade day.
  * Only a PRESENT stamp that DISAGREES with the live set is stale. Both md5
    and persona_count must agree when both sides carry them.
  * Fail-open on any read error: UNKNOWN serves (and is never labelled fresh).
  * This module is the single home of the READ side of the fleet's own stamps
    (``.persona-set-version`` written by ``shared-utils/provision-persona-index.sh``
    and the manifest's release tag, mirrored on disk as the existing
    ``.prebuilt-index-version`` sentinel). It adds no new writer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

__version__ = "1.0.0"
__all__ = ["check_index_freshness", "FreshnessVerdict"]

FRESH = "fresh"
STALE = "stale"
UNKNOWN = "unknown"

# Only these two are truthful to serve on. UNKNOWN is not a staleness finding.
SERVABLE = (FRESH, UNKNOWN)


class FreshnessVerdict(tuple):
    """``(status, reason, served_path)`` — a NamedTuple-shaped 3-tuple.

    ``served_path`` is what the CALLER may serve: ``"semantic"`` for fresh,
    ``"unknown-unverified"`` when no stamp could be read, ``"lexical"`` when
    the index is stale. It is here so a caller cannot report semantic results
    without having asked this question first.
    """

    __slots__ = ()

    def __new__(cls, status: str, reason: str, served_path: str):
        return super().__new__(cls, (status, reason, served_path))

    @property
    def status(self) -> str:
        return self[0]

    @property
    def reason(self) -> str:
        return self[1]

    @property
    def served_path(self) -> str:
        return self[2]

    @property
    def servable(self) -> bool:
        return self.status in SERVABLE


def _md5_file(path: Path) -> str:
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def check_index_freshness(index_dir, categories_path) -> FreshnessVerdict:
    """Is the persona index in ``index_dir`` still current for the live set?

    ``index_dir`` is the directory holding the index DB (``gemini-index.sqlite``)
    and its stamps: ``.persona-set-version`` (fleet stamp: ``md5`` +
    ``persona_count`` + ``lastUpdated``) and ``.prebuilt-index-version``
    (release tag of a prebuilt asset). ``categories_path`` is the live
    ``persona-categories.json`` the box is actually serving. Callers may pass
    None for either; a missing input is UNKNOWN, never stale.

    Returns :class:`FreshnessVerdict`. Never raises.
    """
    try:
        if index_dir is None or categories_path is None:
            return FreshnessVerdict(
                UNKNOWN, "no index dir or persona set supplied", "unknown-unverified"
            )
        index_dir = Path(index_dir)
        categories_path = Path(categories_path)
        if not categories_path.is_file():
            return FreshnessVerdict(
                UNKNOWN, f"live persona set absent ({categories_path.name})",
                "unknown-unverified",
            )
        live = _load_json(categories_path)
        if not live:
            return FreshnessVerdict(
                UNKNOWN, "live persona set unparseable", "unknown-unverified"
            )

        stamp_path = index_dir / ".persona-set-version"
        if not stamp_path.is_file():
            # No stamp: built locally, or box predates the stamp. Not evidence.
            return FreshnessVerdict(
                FRESH, "no index build stamp (legacy/prebuilt-build state)", "semantic"
            )
        stamp = _load_json(stamp_path)
        if not stamp or not stamp.get("md5"):
            return FreshnessVerdict(
                FRESH, "index build stamp carries no md5 (legacy state)", "semantic"
            )

        stamp_md5 = str(stamp["md5"])
        live_md5 = _md5_file(categories_path)
        if not live_md5:
            return FreshnessVerdict(
                UNKNOWN, "live persona set unreadable", "unknown-unverified"
            )
        if stamp_md5 != live_md5:
            return FreshnessVerdict(
                STALE,
                f"index built for persona set md5 {stamp_md5} but the live set "
                f"is {live_md5}",
                "lexical",
            )

        # Same set bytes: the count must agree too, or the stamp is lying.
        live_count = len(live.get("personas") or {})
        stamp_count = stamp.get("persona_count")
        if (isinstance(stamp_count, int) and not isinstance(stamp_count, bool)
                and live_count and stamp_count != live_count):
            return FreshnessVerdict(
                STALE,
                f"index built for {stamp_count} personas but the live set has "
                f"{live_count}",
                "lexical",
            )
        return FreshnessVerdict(FRESH, "index build stamp matches the live set",
                                "semantic")
    except Exception as exc:  # fail-open: a hiccup is never evidence of staleness
        return FreshnessVerdict(
            UNKNOWN, f"freshness check error ({type(exc).__name__})",
            "unknown-unverified",
        )
