"""Shared path-comparison helpers for the launcher suite (FIX-06).

Two spellings of one filesystem object must compare equal: on macOS ``/var`` and
``/tmp`` are symlinks to ``/private/var`` and ``/private/tmp``, so a test that
compares recorded strings rejects the same file written two ways. Every path
comparison in this suite goes through these helpers so the defect cannot recur
test by test.

This is the test side. The production side of the same comparison is FIX-13 in
``83-black-friday-launcher/launcher_core/launch_bridge.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Set, Tuple


def canonical(path: Any) -> Path:
    """The resolved form of one path: filesystem identity, not spelling."""
    return Path(str(path)).resolve()


def same_path(left: Any, right: Any) -> bool:
    """True when both paths name the same filesystem object, whichever spelling."""
    return canonical(left) == canonical(right)


def artifact_identity(rows: Iterable[Any]) -> Set[Tuple[str, str]]:
    """The identity set of artifact rows: (canonical path, sha256).

    Compares what a row names, so an absolute row recorded under ``/tmp`` and
    the same file re-listed under ``/private/tmp`` are one entry, not two.
    """
    out: Set[Tuple[str, str]] = set()
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("path"), str):
            out.add((str(canonical(row["path"])), row.get("sha256")))
    return out
