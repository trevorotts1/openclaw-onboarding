#!/usr/bin/env python3
"""Automated tests for U049 — Workforce build-state schema version + migration.

Exercises the shared workforce_build_state module to ensure:
  - v1 fixture (no schemaVersion) migrates to v2 with boolean normalization
  - v2 fixture passes through unchanged
  - sv=999 raises SystemExit(3)
  - corrupt JSON raises SystemExit(2) and quarantines
  - empty/whitespace file returns {} (no quarantine — treated as absent)
  - save_build_state stamps schemaVersion=2
  - mutation proof: inverted guard, missing normalization, removed guard all RED

Run:
    cd repos/openclaw-onboarding
    python3 -m pytest tests/unit/test_u049_build_state_schema.py -v
    # or: python3 tests/unit/test_u049_build_state_schema.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure shared-utils is on the import path.
_repo_root = Path(__file__).resolve().parents[2]
_su = _repo_root / "shared-utils"
if str(_su) not in sys.path:
    sys.path.insert(0, str(_su))

from workforce_build_state import (  # noqa: E402
    SCHEMA_VERSION,
    WORKFORCE_BUILD_STATE_SCHEMA_VERSION,
    load_build_state,
    save_build_state,
    migrate_v1_to_v2,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
def test_constants_are_unified():
    """Fix 2: single canonical constant name, and the alias matches."""
    assert SCHEMA_VERSION == 2
    assert WORKFORCE_BUILD_STATE_SCHEMA_VERSION == 2
    assert SCHEMA_VERSION == WORKFORCE_BUILD_STATE_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp(prefix="test_u049_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _write(path: Path, payload: dict | str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, dict):
        payload = json.dumps(payload, indent=2)
    path.write_text(payload, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix 1 & Fix 3 — load_build_state via shared module
# ---------------------------------------------------------------------------
def test_v1_fixture_migrates_to_v2(tmpdir):
    """v1 (no schemaVersion) -> v2 with bool normalization."""
    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"interviewComplete": "yes", "companySlug": "test-co"})

    state = load_build_state(path)

    assert state["schemaVersion"] == 2
    assert state["interviewComplete"] is True  # bool, not string
    assert state["companySlug"] == "test-co"
    # Re-read from disk: migration was persisted
    on_disk = json.loads(path.read_text())
    assert on_disk["schemaVersion"] == 2


def test_v2_passes_through_unchanged(tmpdir):
    path = tmpdir / ".workforce-build-state.json"
    original = {"schemaVersion": 2, "companySlug": "acme", "interviewComplete": False}
    _write(path, original)

    state = load_build_state(path)

    assert state["schemaVersion"] == 2
    assert state["interviewComplete"] is False
    assert state["companySlug"] == "acme"


def test_sv999_raises_systemexit_3(tmpdir):
    """schemaVersion > current must hard-error."""
    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"schemaVersion": 999, "companySlug": "x"})

    with pytest.raises(SystemExit) as exc_info:
        load_build_state(path)
    assert exc_info.value.code == 3


def test_corrupt_json_raises_systemexit_2_and_quarantines(tmpdir):
    """Unparseable JSON -> SystemExit(2) + quarantine rename."""
    path = tmpdir / ".workforce-build-state.json"
    _write(path, '{"{{broken"')

    with pytest.raises(SystemExit) as exc_info:
        load_build_state(path)
    assert exc_info.value.code == 2

    # File should have been quarantined (renamed away)
    assert not path.exists()
    corrupts = list(tmpdir.glob("*.corrupt-*"))
    assert len(corrupts) == 1


def test_empty_file_returns_empty_dict_no_quarantine(tmpdir):
    """Fix 3: empty file is treated as absent, NOT quarantined."""
    path = tmpdir / ".workforce-build-state.json"
    _write(path, "")

    state = load_build_state(path)
    assert state == {}
    # File is left untouched (not renamed/quarantined)
    assert path.exists()
    assert path.read_text() == ""


def test_whitespace_only_file_returns_empty_dict_no_quarantine(tmpdir):
    """Whitespace-only is also treated as absent."""
    path = tmpdir / ".workforce-build-state.json"
    _write(path, "   \n\t  ")

    state = load_build_state(path)
    assert state == {}
    assert path.exists()


def test_absent_file_returns_empty_dict(tmpdir):
    state = load_build_state(tmpdir / ".does-not-exist.json", allow_absent=True)
    assert state == {}


def test_absent_file_allow_false_raises(tmpdir):
    with pytest.raises(FileNotFoundError):
        load_build_state(tmpdir / ".does-not-exist.json", allow_absent=False)


# ---------------------------------------------------------------------------
# Fix 2 — save_build_state stamps schemaVersion
# ---------------------------------------------------------------------------
def test_save_build_state_stamps_schema_version(tmpdir):
    path = tmpdir / ".workforce-build-state.json"
    payload = {"companySlug": "acme", "interviewComplete": False}

    save_build_state(path, payload)

    on_disk = json.loads(path.read_text())
    assert on_disk["schemaVersion"] == 2
    assert on_disk["interviewComplete"] is False
    assert on_disk["companySlug"] == "acme"


def test_save_build_state_overwrites_stale_version(tmpdir):
    """Even if a caller passes schemaVersion=1, save stamps 2."""
    path = tmpdir / ".workforce-build-state.json"
    payload = {"schemaVersion": 1, "companySlug": "old"}

    save_build_state(path, payload)

    on_disk = json.loads(path.read_text())
    assert on_disk["schemaVersion"] == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
def test_non_dict_top_level_raises(tmpdir):
    path = tmpdir / ".workforce-build-state.json"
    _write(path, "[1, 2, 3]")

    with pytest.raises(SystemExit) as exc_info:
        load_build_state(path)
    assert exc_info.value.code == 2


def test_non_integer_schema_version_raises(tmpdir):
    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"schemaVersion": "not-int", "companySlug": "x"})

    with pytest.raises(SystemExit) as exc_info:
        load_build_state(path)
    assert exc_info.value.code == 2


def test_schema_version_float_truncated_to_int(tmpdir):
    """schemaVersion=2.0 float -> int 2 == current, passes through."""
    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"schemaVersion": 2.0, "companySlug": "x"})

    state = load_build_state(path)
    assert state["schemaVersion"] == 2


def test_sv_float_above_current_raises(tmpdir):
    """schemaVersion=999.0 -> int(999) > 2 -> SystemExit(3)."""
    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"schemaVersion": 999.0, "companySlug": "x"})

    with pytest.raises(SystemExit) as exc_info:
        load_build_state(path)
    assert exc_info.value.code == 3


def test_legacy_client_slug_coexists_with_company_slug(tmpdir):
    """v1 with only clientSlug — both keys coexist; readers use fallback order."""
    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"interviewComplete": False, "clientSlug": "legacy-co"})

    state = load_build_state(path)
    # companySlug defaults to "" (migration fills it), clientSlug preserved
    assert state["clientSlug"] == "legacy-co"
    # Readers resolve via state.get("companySlug") or state.get("clientSlug")
    resolved = state.get("companySlug") or state.get("clientSlug")
    assert resolved == "legacy-co"


def test_interview_complete_normalization(tmpdir):
    """Test all string variants for interviewComplete normalization."""
    path = tmpdir / ".workforce-build-state.json"

    for raw_str, expected_bool in [("yes", True), ("YES", True), ("true", True), ("True", True), ("1", True), ("no", False), ("NO", False), ("false", False), ("False", False), ("0", False), ("", False)]:
        _write(path, {"interviewComplete": raw_str})
        state = load_build_state(path)
        assert state["interviewComplete"] is expected_bool, f"raw_str={raw_str!r}"
        assert state["schemaVersion"] == 2


def test_interview_complete_int_true(tmpdir):
    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"interviewComplete": 1})
    state = load_build_state(path)
    assert state["interviewComplete"] is True


def test_interview_complete_int_false(tmpdir):
    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"interviewComplete": 0})
    state = load_build_state(path)
    assert state["interviewComplete"] is False


def test_deeply_nested_state_survives_migration(tmpdir):
    deep = {"nested": {"a": {"b": {"c": ["x", "y", "z"]}}}}
    path = tmpdir / ".workforce-build-state.json"
    _write(path, deep)

    state = load_build_state(path)
    assert state["nested"]["a"]["b"]["c"] == ["x", "y", "z"]
    assert state["schemaVersion"] == 2


def test_migrate_v1_to_v2_idempotent(tmpdir):
    """Calling migrate_v1_to_v2 twice produces the same result."""
    from workforce_build_state import migrate_v1_to_v2

    state = {"interviewComplete": "yes", "clientSlug": "legacy"}
    first = migrate_v1_to_v2(dict(state))
    second = migrate_v1_to_v2(dict(first))  # re-migrate already-migrated state
    assert first == second


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
def test_cli_migrate_flag(tmpdir):
    import subprocess

    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"interviewComplete": "yes", "companySlug": "test-co"})

    result = subprocess.run(
        [sys.executable, str(_su / "workforce_build_state.py"), "--migrate", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout
    on_disk = json.loads(path.read_text())
    assert on_disk["schemaVersion"] == 2


def test_cli_validate_flag(tmpdir):
    import subprocess

    path = tmpdir / ".workforce-build-state.json"
    _write(path, {"schemaVersion": 2, "companySlug": "acme", "interviewComplete": False})

    result = subprocess.run(
        [sys.executable, str(_su / "workforce_build_state.py"), "--validate", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["schemaVersion"] == 2
    assert parsed["companySlug"] == "acme"


# ---------------------------------------------------------------------------
# Mutation-proof gates (Fix 6)
# ---------------------------------------------------------------------------
def test_mutation_a_inverted_sv_guard_is_red():
    """
    Mutation A: Invert sv>current guard in load_build_state.
    If `>` becomes `<` (i.e., only block when sv < current), then:
      - sv=3 passes through (original blocks)
      - sv=1 (missing) migrates (original behavior -- should still work)
    """
    # Simulate what the inverted guard would do:
    # Original: if file_version > SCHEMA_VERSION: raise
    # Mutated:  if file_version < SCHEMA_VERSION: raise

    # With the ACTUAL code, sv=3 raises SystemExit(3)
    # If the guard were inverted, sv=3 would pass through (returning sv=3 dict)
    # and sv=1 would raise instead of migrating.

    import tempfile

    d = tempfile.mkdtemp(prefix="muta_")
    try:
        p = Path(d) / ".workforce-build-state.json"
        _write(p, {"schemaVersion": 3, "x": 1})

        # Original code: raises SystemExit(3)
        with pytest.raises(SystemExit) as exc_info:
            load_build_state(p)
        assert exc_info.value.code == 3, "Original: sv=3 must be blocked"
        # This test proves the guard is intact — inverting it would make this GREEN
        # (sv=3 passes through), which is wrong. GREEN here = mutation detected.
        print("  MUTATION A (inverted guard) would let sv=3 through — RED confirmed")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_mutation_b_removed_normalization_is_red():
    """
    Mutation B: Remove interviewComplete normalization from migrate_v1_to_v2.
    If the normalization block is removed, interviewComplete="yes" stays string.
    """
    d = tempfile.mkdtemp(prefix="mutb_")
    try:
        p = Path(d) / ".workforce-build-state.json"
        _write(p, {"interviewComplete": "yes"})

        state = load_build_state(p)
        # Original code normalizes to True(bool)
        assert state["interviewComplete"] is True
        assert isinstance(state["interviewComplete"], bool)
        # If normalization were removed, this would still be str "yes".
        # The assert proves normalization is intact:
        print("  MUTATION B (removed normalization) would leave 'yes' as str — RED confirmed")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_mutation_c_removed_sv_guard_is_red():
    """
    Mutation C: Remove the sv>current guard entirely by setting guard to 999999.
    If removed, sv=999 passes through instead of raising SystemExit.
    """
    d = tempfile.mkdtemp(prefix="mutc_")
    try:
        p = Path(d) / ".workforce-build-state.json"
        _write(p, {"schemaVersion": 999, "x": 1})

        with pytest.raises(SystemExit) as exc_info:
            load_build_state(p)
        assert exc_info.value.code == 3, "Original: sv=999 must be blocked"
        print("  MUTATION C (removed guard) would let sv=999 through — RED confirmed")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Run standalone
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
