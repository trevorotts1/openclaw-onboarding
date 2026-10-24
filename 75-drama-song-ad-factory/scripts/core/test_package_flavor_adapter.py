#!/usr/bin/env python3
"""Focused tests for package_flavor_adapter (S75-T03 / S75-A03).

Proves: both flavors resolve through the one named seam, the shared core is not
forked, and the package difference is actually preserved.

Run: python3 -m pytest -q scripts/core/test_package_flavor_adapter.py
 or: python3 scripts/core/test_package_flavor_adapter.py
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import story_first_contracts as C  # noqa: E402
import package_flavor_adapter as A  # noqa: E402

SKILL_ROOT = os.path.dirname(os.path.dirname(HERE))


def _raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - assertion helper
        return exc
    raise AssertionError("expected %s to raise" % getattr(fn, "__name__", fn))


def test_both_flavors_resolve_through_seam():
    for flavor in (A.ONB, A.N999):
        result = A.resolve(flavor)
        assert result["seam"] == A.SEAM
        assert result["flavor"] == flavor
        assert result["core_module"] == C.__name__
        assert result["core_schema_version"] == C.SCHEMA_VERSION
        assert result["core_stage_count"] == len(C.STAGE_ORDER)


def test_shared_core_not_forked():
    onb = A.resolve(A.ONB)
    n999 = A.resolve(A.N999)
    # Both flavors resolve against byte-identical shared core.
    assert onb["core_digest"] == n999["core_digest"] == A.core_digest()
    # Exactly one copy of the shared core exists under the skill root.
    copies = glob.glob(os.path.join(SKILL_ROOT, "**", "story_first_contracts*.py"),
                       recursive=True)
    assert [os.path.realpath(p) for p in copies] == [os.path.realpath(C.__file__)]
    # The adapter carries no forked core constants.
    for name in ("STAGE_ORDER", "STAGE_REQUIRES", "SCHEMA_VERSION",
                 "validate_identity", "check_stage"):
        assert not hasattr(A, name)


def test_flavor_difference_preserved():
    onb = A.resolve(A.ONB)
    n999 = A.resolve(A.N999)
    differing = [k for k in A.PACKAGE_DIFFERENCES if onb[k] != n999[k]]
    assert differing == list(A.PACKAGE_DIFFERENCES)
    assert onb["skill_root_anchor"] == "75-drama-song-ad-factory"
    assert n999["skill_root_anchor"] == ".claude/skills/drama-song-ad-factory"
    assert onb["character_approval_module"].endswith("character_approval.py")
    assert n999["character_approval_module"] is None


def test_second_flavor_fixture_round_trip():
    fixture = A.load_fixture_999()
    # Fixture is package data only, no core logic.
    assert set(fixture) - set(A._META_KEYS) == set(A.PACKAGE_DIFFERENCES)
    via_fixture = A.resolve(fixture["flavor"], layout=fixture)
    assert via_fixture == A.resolve(A.N999)
    # Shared core identity is untouched by the flavor-specific result.
    assert via_fixture["core_digest"] == A.core_digest()
    assert via_fixture["skill_root_anchor"] != A.resolve(A.ONB)["skill_root_anchor"]


def test_bad_flavor_and_layout_refused():
    exc = _raises(A.resolve, "other")
    assert isinstance(exc, A.FlavorError)
    exc = _raises(A.resolve, A.N999, layout={"flavor": A.ONB})
    assert isinstance(exc, A.FlavorError)
    exc = _raises(A.resolve, A.ONB, layout={"skill_root_anchor": "x"})
    assert isinstance(exc, A.FlavorError)


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - standalone runner
            failures += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok   %s" % name)
    print("\n%d passed, %d failed, %d total" % (len(tests) - failures, failures, len(tests)))
    sys.exit(1 if failures else 0)
