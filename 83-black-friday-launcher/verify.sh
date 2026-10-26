#!/usr/bin/env bash
# Read-only verification for the launcher core. Exit 0 pass, non-zero fail.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# One interpreter for every step below, and it must be dependency-complete.
# L25-BF-40 was exactly the split this removes: an isolated interpreter hid
# user site-packages and reported jsonschema missing while the plain one
# reported it present, so the route tests and check_package could accept a
# missing validator. There is no isolated step left.
PY="${PYTHON:-python3}"

echo "== interpreter: $PY =="
"$PY" - <<'PREFLIGHT'
import importlib.util
import sys

missing = [name for name in ("jsonschema",)
           if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(
        "verify: %s is not importable under %s. The Skill 79 checkout validator "
        "cannot load, so verification would accept a missing validator. Install "
        "the runtime requirement first: %s -m pip install -r requirements.txt"
        % (", ".join(missing), sys.executable, sys.executable))
print("dependency-complete interpreter:", sys.executable)
print("runtime requirement present:", ", ".join(("jsonschema",)))
PREFLIGHT

echo "== open and decided seams =="
"$PY" -m launcher_core.cli seams

echo "== unit + integration checks =="
"$PY" -m unittest discover -s tests -p 'test_*.py' -v

echo "== route invariants, adapter wiring and the offline browser diagnostic =="
# BrowserDiagnosticTests lives in this file and runs here exactly once, through
# discovery. It probes this machine for browser tooling, prints exactly what it
# found, and proves the landing -> checkout route wiring and the Skill 79 order
# form binding without driving a browser; a failure fails this script.
"$PY" -m unittest discover -s "$HERE/routes/tests" -p 'test_routes.py' -v

echo "== worked-example fixtures =="
"$PY" "$HERE/fixtures/run_fixtures.py"

echo "== 999 dependency package =="
"$PY" -m launcher_core.cli dependencies
