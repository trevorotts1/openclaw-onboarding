"""clip_checks: measured and vision checks that gate pictures, clips, takes and
the master (sections 3B.4, 3C.7, 3C.9, 3C.10, 3J, 3K, 3M.4).

Every finding carries MINOR / MEDIUM / MAJOR from :mod:`severity`; only MAJOR
stops that one item or sends it to a remake (section 3J). Every check fails
closed: a check that could not run is MAJOR item 15, never a pass.

stdlib only, no network, no spend. Detectors are injected, so each module can
be proved without a real video.
"""
from __future__ import annotations

from . import severity  # noqa: F401

__all__ = ["severity"]
