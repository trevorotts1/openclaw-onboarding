"""manifest_assert.py drift guard.

manifest_assert.py mirrors MIN_MANIFEST_VERSION from presentation_job/manifest.py
by hand (its own module docstring: "Bump the two TOGETHER -- a floor one behind
the manifest is the split-brain this check exists to prevent"). Nothing enforced
that promise until now -- the floor drifted to 43 while the engine and the real
manifest moved to 48, and no test caught it. This test pins the two together so a
future bump to one without the other fails the suite instead of shipping a
defense-in-depth gate with no teeth.

Flat file beside the code it tests, matching every sibling in this directory
(e.g. test_gates.py): no shared configuration file, own import path.
"""
from __future__ import annotations

import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import manifest_assert  # noqa: E402
from presentation_job.manifest import MIN_MANIFEST_VERSION as ENGINE_MIN_MANIFEST_VERSION  # noqa: E402


def test_manifest_assert_floor_matches_engine_floor():
    assert manifest_assert.MIN_MANIFEST_VERSION == ENGINE_MIN_MANIFEST_VERSION, (
        f"manifest_assert.MIN_MANIFEST_VERSION ({manifest_assert.MIN_MANIFEST_VERSION}) "
        f"must equal presentation_job.manifest.MIN_MANIFEST_VERSION "
        f"({ENGINE_MIN_MANIFEST_VERSION}) -- a gap here is the exact split-brain "
        "manifest_assert.py's own header comment says this mirror exists to prevent.")
