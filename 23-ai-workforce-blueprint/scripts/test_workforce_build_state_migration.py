#!/usr/bin/env python3
"""Guard the build-state v1 -> v2 migration (BU-36).

Three behaviours this test pins, each one a way the migration could silently
damage an owner's box:

  1. A non-standard completion value — the word "complete", for example — is
     LEFT AS FOUND. The migration used to turn it into ``false``, which
     un-completed a finished interview. It now keeps the value and records why
     in ``schemaMigrationWarnings``.
  2. A real boolean is still normalized to itself (``true`` stays ``true``).
  3. An unparseable file keeps its own name: quarantine COPIES the bytes to
     ``<name>.corrupt-<time>`` and never moves the original away, so a corrupt
     box can no longer look like a box with no state at all.

Run directly (``python3 test_workforce_build_state_migration.py``) or under a
test runner; both work.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# workforce_build_state.py lives in this repository's top-level shared-utils/,
# three levels up from this file (scripts -> blueprint -> repository root).
SHARED_UTILS = Path(__file__).resolve().parents[2] / "shared-utils"
if str(SHARED_UTILS) not in sys.path:
    sys.path.insert(0, str(SHARED_UTILS))

from workforce_build_state import SCHEMA_VERSION, load_build_state  # noqa: E402


def _new_state_file(payload):
    """A fresh .workforce-build-state.json in its own temp folder."""
    directory = Path(tempfile.mkdtemp(prefix="wbs-migration-"))
    path = directory / ".workforce-build-state.json"
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path


def test_non_standard_completion_value_is_left_untouched():
    path = _new_state_file({"interviewComplete": "complete"})

    state = load_build_state(path)

    assert state.get("schemaVersion") == SCHEMA_VERSION, state.get("schemaVersion")
    assert state.get("interviewComplete") == "complete", (
        "the migration rewrote an owner's completion value: "
        f"{state.get('interviewComplete')!r}"
    )
    warnings = state.get("schemaMigrationWarnings")
    assert isinstance(warnings, list), f"schemaMigrationWarnings is {warnings!r}"
    assert len(warnings) == 1, f"expected one warning, got {warnings!r}"
    assert "complete" in warnings[0], warnings[0]

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk.get("interviewComplete") == "complete", on_disk.get("interviewComplete")
    assert on_disk.get("schemaMigrationWarnings") == warnings


def test_booleans_are_still_normalized():
    for value in (True, False):
        path = _new_state_file({"interviewComplete": value})
        state = load_build_state(path)
        assert state.get("interviewComplete") is value, (
            f"{value!r} came back as {state.get('interviewComplete')!r}"
        )
        assert not state.get("schemaMigrationWarnings"), state.get("schemaMigrationWarnings")


def test_unparseable_file_keeps_its_name():
    path = _new_state_file("{ this is not json")
    try:
        load_build_state(path)
    except SystemExit as exc:
        assert exc.code == 2, f"expected SystemExit(2), got {exc.code!r}"
    else:
        raise AssertionError("an unparseable file must raise SystemExit(2)")

    assert path.exists(), "the original file was moved away instead of copied"
    assert path.read_text(encoding="utf-8") == "{ this is not json", "the original bytes changed"

    copies = sorted(path.parent.glob(path.name + ".corrupt-*"))
    assert len(copies) == 1, f"expected one .corrupt copy, found {copies}"


def _main() -> int:
    failures = 0
    for name in sorted(n for n in globals() if n.startswith("test_")):
        function = globals()[name]
        if not callable(function):
            continue
        try:
            function()
        except Exception as exc:  # noqa: BLE001 - a plain runner reports, never hides
            failures += 1
            print(f"FAIL {name}: {exc}")
        else:
            print(f"PASS {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())
