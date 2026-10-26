"""Package-flavor adapter for Skill 75 (S75-T03 / S75-A03). Stdlib only.

The shared story-first core (story_first_contracts) is flavor-neutral. The two
package flavors differ in exactly two package-level facts, both preserved here:

  onboarding (ONB) - skill root anchor `75-drama-song-ad-factory`, package-local
      `scripts/core/character_bible/character_approval.py`.
  999 (N999) - skill root anchor `.claude/skills/drama-song-ad-factory`; the
      sampled layout has no `character_bible/character_approval.py`.

`resolve()` is the single named seam (SEAM). Both flavors resolve through it
against the same shared core bytes. Flavor data lives in the profiles and in the
second-flavor fixture `contracts/flavor-999.json`; no core logic is forked per
flavor. Importing this module has no side effects.
"""
from __future__ import annotations

import hashlib
import json
import os

import story_first_contracts as core

SEAM = "package_flavor_adapter.resolve"

ONB = "onboarding"
N999 = "999"
FLAVORS = (ONB, N999)

# The complete set of preserved package differences. Anything not listed here
# is shared core behavior and must never be forked per flavor.
PACKAGE_DIFFERENCES = ("skill_root_anchor", "character_approval_module")

FLAVOR_999_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "contracts", "flavor-999.json")

_PROFILES = {
    ONB: {
        "skill_root_anchor": "75-drama-song-ad-factory",
        "character_approval_module": "scripts/core/character_bible/character_approval.py",
    },
    N999: {
        "skill_root_anchor": ".claude/skills/drama-song-ad-factory",
        "character_approval_module": None,
    },
}

_META_KEYS = ("flavor", "provenance")


class FlavorError(Exception):
    """Unknown flavor or layout that does not carry the package differences."""


def core_digest():
    """Digest of the one shared core module both flavors resolve against."""
    with open(core.__file__, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_fixture_999():
    """Read the second-flavor (999) package-layout fixture."""
    with open(FLAVOR_999_FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def resolve(flavor, layout=None):
    """The single named seam: map one package layout onto the shared core."""
    if flavor not in FLAVORS:
        raise FlavorError("unknown package flavor: %r" % (flavor,))
    if layout is None:
        layout = _PROFILES[flavor]
    else:
        if layout.get("flavor", flavor) != flavor:
            raise FlavorError("layout flavor %r does not match %r"
                              % (layout.get("flavor"), flavor))
        missing = [k for k in PACKAGE_DIFFERENCES if k not in layout]
        if missing:
            raise FlavorError("layout missing package differences: %s" % missing)
    return {
        "seam": SEAM,
        "flavor": flavor,
        "skill_root_anchor": layout["skill_root_anchor"],
        "character_approval_module": layout["character_approval_module"],
        "core_module": core.__name__,
        "core_schema_version": core.SCHEMA_VERSION,
        "core_stage_count": len(core.STAGE_ORDER),
        "core_digest": core_digest(),
    }
