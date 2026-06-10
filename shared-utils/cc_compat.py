#!/usr/bin/env python3
"""
cc_compat.py — Shared cc-compat.json resolver (PRD 1.11, Decision 2).

Used by TWO readers:
  1. shared-utils/fleet_refresh_runner.py  — resolves cc_tag for git checkout
     and asserts deployed CC >= minVersion.
  2. 32-command-center-setup installer scripts — checks out the pinned/>=minVersion
     CC tag on fresh install (instead of bare main).

Importing pattern:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))   # shared-utils
    from cc_compat import load_cc_compat, resolve_cc_tag, assert_min_version

Single source: this module. Do NOT duplicate the resolution logic anywhere else.

PRD 1.11 — v11.5.0
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _parse_semver(v: str) -> tuple[int, int, int]:
    """Parse 'vMAJOR.MINOR.PATCH' or 'MAJOR.MINOR.PATCH' → (major, minor, patch).
    Raises ValueError on unparseable input."""
    v = v.lstrip("v").strip()
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)', v)
    if not m:
        raise ValueError(f"Cannot parse version string: {v!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _version_gte(a: str, b: str) -> bool:
    """Return True if version a >= version b."""
    return _parse_semver(a) >= _parse_semver(b)


def _version_lte(a: str, b: str) -> bool:
    """Return True if version a <= version b."""
    return _parse_semver(a) <= _parse_semver(b)


# ---------------------------------------------------------------------------
# Load cc-compat.json
# ---------------------------------------------------------------------------

def load_cc_compat(repo_root: Optional[Path] = None) -> dict:
    """
    Load and validate cc-compat.json from the onboarding repo root.

    Args:
        repo_root: Path to the repo root.  If None, walks up from this file's
                   location (shared-utils/ → parent = repo root).

    Returns:
        Parsed cc-compat dict with schemaVersion, onboardingVersion, commandCenter.*

    Raises:
        FileNotFoundError: if cc-compat.json is not present.
        ValueError: if required fields are missing or malformed.
    """
    if repo_root is None:
        # shared-utils lives one level below repo root
        repo_root = Path(__file__).parent.parent

    compat_path = repo_root / "cc-compat.json"
    if not compat_path.is_file():
        raise FileNotFoundError(
            f"cc-compat.json not found at {compat_path}. "
            "This file must exist at the repo root (PRD 1.11 Decision 2)."
        )

    try:
        data = json.loads(compat_path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"cc-compat.json is not valid JSON: {e}") from e

    # Validate required fields
    _validate_cc_compat(data, compat_path)
    return data


def _validate_cc_compat(data: dict, source: Path) -> None:
    """Raise ValueError if any required field is missing or malformed."""
    if data.get("schemaVersion") != 1:
        raise ValueError(f"cc-compat.json schemaVersion must be 1, got: {data.get('schemaVersion')!r}")

    onboarding_ver = data.get("onboardingVersion", "")
    if not onboarding_ver or not re.match(r'^v\d+\.\d+\.\d+', onboarding_ver):
        raise ValueError(f"cc-compat.json onboardingVersion must be vX.Y.Z, got: {onboarding_ver!r}")

    cc = data.get("commandCenter", {})
    if not isinstance(cc, dict):
        raise ValueError("cc-compat.json commandCenter must be an object")

    min_ver = cc.get("minVersion", "")
    if not min_ver or not re.match(r'^v\d+\.\d+\.\d+', min_ver):
        raise ValueError(f"cc-compat.json commandCenter.minVersion must be vX.Y.Z, got: {min_ver!r}")

    pinned = cc.get("pinnedTag")
    if pinned is not None:
        if not re.match(r'^v\d+\.\d+\.\d+', str(pinned)):
            raise ValueError(
                f"cc-compat.json commandCenter.pinnedTag must be vX.Y.Z or null, got: {pinned!r}"
            )
        if not _version_gte(pinned, min_ver):
            raise ValueError(
                f"cc-compat.json pinnedTag ({pinned}) < minVersion ({min_ver}): "
                "pinnedTag must be >= minVersion"
            )

    max_ver = cc.get("maxVersion")
    if max_ver is not None:
        if not re.match(r'^v\d+\.\d+\.\d+', str(max_ver)):
            raise ValueError(
                f"cc-compat.json commandCenter.maxVersion must be vX.Y.Z or null, got: {max_ver!r}"
            )


# ---------------------------------------------------------------------------
# Resolve CC tag
# ---------------------------------------------------------------------------

def resolve_cc_tag(compat: dict, available_tags: Optional[list[str]] = None) -> str:
    """
    Resolve the Command Center git tag to check out.

    Resolution rule (PRD Decision 2):
        cc_tag = pinnedTag                             if pinnedTag is set
                 else highest T in available_tags
                      such that minVersion <= T <= (maxVersion or +inf)

    Args:
        compat:          Loaded cc-compat.json dict (from load_cc_compat()).
        available_tags:  List of 'vX.Y.Z' strings from `git tag` on the CC repo.
                         Required when pinnedTag is null.

    Returns:
        The resolved tag string, e.g. "v4.14.0".

    Raises:
        ValueError: if pinnedTag is null and no eligible tag is found among
                    available_tags.
    """
    cc = compat["commandCenter"]
    min_ver  = cc["minVersion"]
    max_ver  = cc.get("maxVersion")
    pinned   = cc.get("pinnedTag")

    if pinned:
        return pinned

    # Resolve from available_tags
    if not available_tags:
        raise ValueError(
            "cc-compat.json pinnedTag is null: available_tags must be provided to "
            "resolve the latest CC tag >= minVersion."
        )

    eligible = []
    for tag in available_tags:
        tag = tag.strip()
        if not re.match(r'^v\d+\.\d+\.\d+', tag):
            continue
        try:
            if _version_gte(tag, min_ver) and (max_ver is None or _version_lte(tag, max_ver)):
                eligible.append(tag)
        except ValueError:
            continue

    if not eligible:
        raise ValueError(
            f"No CC tag found in available_tags that satisfies "
            f"minVersion={min_ver} <= tag <= {max_ver or 'unbounded'}. "
            f"Available: {available_tags[:10]}"
        )

    # Sort descending and return highest
    eligible.sort(key=_parse_semver, reverse=True)
    return eligible[0]


# ---------------------------------------------------------------------------
# Assert deployed version
# ---------------------------------------------------------------------------

def assert_min_version(deployed_version: str, compat: dict) -> None:
    """
    Assert that the deployed CC version satisfies minVersion.

    Args:
        deployed_version: The CC version string from the deployed package.json.
        compat:           Loaded cc-compat dict.

    Raises:
        ValueError: with a clear message if the version constraint is not met.
    """
    min_ver = compat["commandCenter"]["minVersion"]
    if not _version_gte(deployed_version, min_ver):
        raise ValueError(
            f"Deployed Command Center version {deployed_version!r} is older than "
            f"required minVersion {min_ver!r} from cc-compat.json. "
            "Run fleet-refresh.sh --apply to upgrade."
        )


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick self-test / load-check
    try:
        compat = load_cc_compat()
        print(f"cc-compat.json loaded OK:")
        print(f"  onboardingVersion : {compat['onboardingVersion']}")
        print(f"  minVersion        : {compat['commandCenter']['minVersion']}")
        print(f"  pinnedTag         : {compat['commandCenter'].get('pinnedTag')}")
        print(f"  maxVersion        : {compat['commandCenter'].get('maxVersion')}")
        # Smoke-test resolve_cc_tag with a fake available_tags list
        if compat["commandCenter"].get("pinnedTag"):
            tag = resolve_cc_tag(compat)
        else:
            tag = resolve_cc_tag(compat, available_tags=["v4.12.0", "v4.14.0", "v4.15.0"])
        print(f"  resolved cc_tag   : {tag}")
        print("cc_compat.py self-test PASSED")
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
