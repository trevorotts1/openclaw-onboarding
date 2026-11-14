#!/usr/bin/env python3
"""BU-73 acceptance test: one model lookup per department.

_resolve_director_model is replaced with a counter that returns None and
OPENCLAW_CONFIG points at a config with no default model. determine_specialists
("marketing", ...) must still return its specialist list, must ask the resolver
exactly once, and must not raise (the old code looked the model up inside the
per-role loop, so the failure escaped the department).

Exit 0 = the guard passes; non-zero = it failed. Hermetic: temp folders only.
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "build-workforce.py"


def main() -> int:
    with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory() as home:
        scratch_path = Path(scratch)
        home_path = Path(home)

        config_path = scratch_path / "openclaw.json"
        config_path.write_text(json.dumps({"agents": {"defaults": {}}}), encoding="utf-8")

        os.environ["HOME"] = str(home_path)

        spec = importlib.util.spec_from_file_location("build_workforce_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        module.OPENCLAW_CONFIG = str(config_path)

        calls = {"n": 0}

        def _counter(dept_id):
            calls["n"] += 1
            return None

        module._resolve_director_model = _counter

        try:
            specialists, _context = module.determine_specialists(
                "marketing", {}, {"department_activities": "weekly campaign and follow up"})
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: determine_specialists raised {type(exc).__name__}: {exc}")
            return 1

        if not specialists:
            print("FAIL: determine_specialists returned an empty list")
            return 1
        if calls["n"] != 1:
            print(f"FAIL: resolver called {calls['n']} times, expected 1")
            return 1

    print("PASS: one model lookup per department, specialists returned, no exception")
    return 0


if __name__ == "__main__":
    sys.exit(main())
