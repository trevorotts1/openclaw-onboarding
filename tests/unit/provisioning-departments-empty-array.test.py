#!/usr/bin/env python3
"""
tests/unit/provisioning-departments-empty-array.test.py
─────────────────────────────────────────────────────────────────────────────
U077 — proves shared-utils/fleet_refresh_runner.py::step_provisioning_completeness()
no longer fails a box whose departments.json is an EMPTY array.

FAIL-FIRST: The pre-fix tree treated `len(depts) == 0` as a FAIL, rejecting a
correctly provisioned fresh box (empty departments.json is the INTENDED shipped
default). The authoritative completeness signal is ROLE-FLOOR (floor-prover +
live departments workspace), not the array length.

TestEmptyArrayPasses reproduces the EXACT scenario from the U077 root-cause:
a fresh box with `departments.json = []` — and asserts the DEPARTMENTS check
is `ok: True`. On the pre-fix tree this assertion FAILS (the bug: ok was False).

TestMissingOrInvalidFails proves the gate still rejects missing/not-a-list files.
TestNonEmptyArrayPasses proves the gate still accepts a well-formed non-empty array.

Mutation proof: mutate the empty-array branch to FAIL, verify RED, revert, verify GREEN.

Run:
    python3 tests/unit/provisioning-departments-empty-array.test.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir(), f"shared-utils not found at {_SHARED_UTILS}"

sys.path.insert(0, str(_SHARED_UTILS))

_spec = importlib.util.spec_from_file_location(
    "fleet_refresh_runner", _SHARED_UTILS / "fleet_refresh_runner.py"
)
assert _spec is not None
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)  # type: ignore

step_provisioning_completeness = mod.step_provisioning_completeness
BoxResult = mod.BoxResult


def _make_box() -> BoxResult:
    """Create a minimal BoxResult for testing."""
    box = BoxResult(box="test-box", dry_run=False)
    box.onboarding_version = "v1.0.0"
    return box


def _run_check(departments_content: str | None) -> dict:
    """
    Run step_provisioning_completeness with a temporary departments.json.

    Args:
        departments_content: JSON string to write, or None to omit the file.

    Returns:
        The result dict from step_provisioning_completeness.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create a minimal company dir structure
        company_dir = tmp / "zero-human-company" / "test-company"
        company_dir.mkdir(parents=True)

        # Write departments.json if content provided
        depts_path = company_dir / "departments.json"
        if departments_content is not None:
            depts_path.write_text(departments_content, encoding="utf-8")

        # Create a minimal personas dir (to avoid PERSONAS gate failure)
        personas_dir = tmp / "coaching-personas" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test-persona").mkdir()
        (personas_dir / "test-persona" / "persona-blueprint.md").write_text("# Test", encoding="utf-8")

        # Build paths dict
        paths = {
            "workspace": str(tmp),
            "company_root": str(tmp / "zero-human-company"),
            "company_dir": str(company_dir),
            "departments_json": str(depts_path),
            "personas_dir": str(personas_dir),
        }

        box = _make_box()
        result = step_provisioning_completeness(
            paths=paths,
            res=box,
            pinned_onboarding_tag="v1.0.0",
        )

        return result


def test_empty_array_passes():
    """
    MAIN BEHAVIOR: An empty departments.json array is the intended fresh-box
    default and must PASS the DEPARTMENTS gate.
    """
    result = _run_check("[]")
    depts_check = result["checks"]["DEPARTMENTS"]

    assert depts_check["ok"] is True, (
        f"FAIL: empty departments.json array should PASS (fresh-box default), "
        f"but got ok={depts_check['ok']}, detail={depts_check['detail']}"
    )
    assert "fresh-box default" in depts_check["detail"].lower(), (
        f"FAIL: detail should mention fresh-box default, got: {depts_check['detail']}"
    )
    print("  ok   — empty departments.json array PASSES (fresh-box default)")


def test_missing_file_fails():
    """
    EDGE CASE: A missing departments.json file must FAIL the gate.
    """
    result = _run_check(None)  # No file created
    depts_check = result["checks"]["DEPARTMENTS"]

    assert depts_check["ok"] is False, (
        f"FAIL: missing departments.json should FAIL, "
        f"but got ok={depts_check['ok']}, detail={depts_check['detail']}"
    )
    assert "missing" in depts_check["detail"].lower() or "not-a-list" in depts_check["detail"].lower(), (
        f"FAIL: detail should mention missing/not-a-list, got: {depts_check['detail']}"
    )
    print("  ok   — missing departments.json FAILS (as expected)")


def test_not_a_list_fails():
    """
    EDGE CASE: A departments.json that is not a list (e.g., a dict) must FAIL.
    """
    result = _run_check('{"foo": "bar"}')
    depts_check = result["checks"]["DEPARTMENTS"]

    assert depts_check["ok"] is False, (
        f"FAIL: non-list departments.json should FAIL, "
        f"but got ok={depts_check['ok']}, detail={depts_check['detail']}"
    )
    assert "not-a-list" in depts_check["detail"].lower(), (
        f"FAIL: detail should mention not-a-list, got: {depts_check['detail']}"
    )
    print("  ok   — non-list departments.json FAILS (as expected)")


def test_non_empty_array_passes():
    """
    EDGE CASE: A well-formed non-empty departments.json array must PASS.
    """
    result = _run_check('[{"name": "engineering"}, {"name": "marketing"}]')
    depts_check = result["checks"]["DEPARTMENTS"]

    assert depts_check["ok"] is True, (
        f"FAIL: non-empty departments.json array should PASS, "
        f"but got ok={depts_check['ok']}, detail={depts_check['detail']}"
    )
    assert "2 departments" in depts_check["detail"], (
        f"FAIL: detail should mention '2 departments', got: {depts_check['detail']}"
    )
    print("  ok   — non-empty departments.json array PASSES (as expected)")


def test_mutation_proof():
    """
    MUTATION PROOF: Mutate the empty-array branch to FAIL, verify RED, revert, verify GREEN.

    This proves the test can detect the exact bug U077 fixes.
    """
    # Read the source
    source_path = _SHARED_UTILS / "fleet_refresh_runner.py"
    original = source_path.read_text(encoding="utf-8")

    # Mutate: change the empty-array branch from PASS to FAIL
    mutated = original.replace(
        '    elif len(depts) == 0:\n        checks.append(("DEPARTMENTS", True,\n                       "empty array (fresh-box default; completeness gated by ROLE-FLOOR)"))',
        '    elif len(depts) == 0:\n        checks.append(("DEPARTMENTS", False,\n                       "MUTATED: empty array should fail"))'
    )

    assert mutated != original, "FAIL: mutation did not change the source"

    try:
        # Write mutated source
        source_path.write_text(mutated, encoding="utf-8")

        # Reload the module and re-bind the function
        _spec.loader.exec_module(mod)  # type: ignore
        step_fn = mod.step_provisioning_completeness

        # Run the test — should FAIL (RED)
        result = _run_check_with_fn("[]", step_fn)
        depts_check = result["checks"]["DEPARTMENTS"]

        assert depts_check["ok"] is False, (
            f"FAIL: mutation proof RED phase failed — empty array should FAIL with mutation, "
            f"but got ok={depts_check['ok']}"
        )
        print("  ok   — mutation proof RED: empty array FAILS with mutation (bug detected)")

    finally:
        # Revert: restore original source
        source_path.write_text(original, encoding="utf-8")

        # Reload the module and re-bind the function
        _spec.loader.exec_module(mod)  # type: ignore
        step_fn = mod.step_provisioning_completeness

        # Run the test — should PASS (GREEN)
        result = _run_check_with_fn("[]", step_fn)
        depts_check = result["checks"]["DEPARTMENTS"]

        assert depts_check["ok"] is True, (
            f"FAIL: mutation proof GREEN phase failed — empty array should PASS after revert, "
            f"but got ok={depts_check['ok']}"
        )
        print("  ok   — mutation proof GREEN: empty array PASSES after revert (bug fixed)")


def _run_check_with_fn(departments_content: str | None, step_fn) -> dict:
    """
    Run step_provisioning_completeness with a given function reference.

    Args:
        departments_content: JSON string to write, or None to omit the file.
        step_fn: The step_provisioning_completeness function to call.

    Returns:
        The result dict from step_provisioning_completeness.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create a minimal company dir structure
        company_dir = tmp / "zero-human-company" / "test-company"
        company_dir.mkdir(parents=True)

        # Write departments.json if content provided
        depts_path = company_dir / "departments.json"
        if departments_content is not None:
            depts_path.write_text(departments_content, encoding="utf-8")

        # Create a minimal personas dir (to avoid PERSONAS gate failure)
        personas_dir = tmp / "coaching-personas" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test-persona").mkdir()
        (personas_dir / "test-persona" / "persona-blueprint.md").write_text("# Test", encoding="utf-8")

        # Build paths dict
        paths = {
            "workspace": str(tmp),
            "company_root": str(tmp / "zero-human-company"),
            "company_dir": str(company_dir),
            "departments_json": str(depts_path),
            "personas_dir": str(personas_dir),
        }

        box = _make_box()
        result = step_fn(
            paths=paths,
            res=box,
            pinned_onboarding_tag="v1.0.0",
        )

        return result


if __name__ == "__main__":
    print("=== U077: provisioning gate departments empty-array tests ===")

    test_empty_array_passes()
    test_missing_file_fails()
    test_not_a_list_fails()
    test_non_empty_array_passes()
    test_mutation_proof()

    print("\n=== all tests passed ===")
