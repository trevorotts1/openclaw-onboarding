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
# The interpreter is resolved ONCE to an absolute path and printed, so a failure
# names the exact Python that ran (Big Fleet Roll row 23: "No module named attrs"
# came from a python3 nobody could identify afterwards). PYTHON=<path> overrides.
PY="$(command -v "${PYTHON:-python3}" || true)"
if [ -z "$PY" ]; then
    echo "verify: interpreter '${PYTHON:-python3}' was not found on PATH" >&2
    exit 1
fi

echo "== interpreter: $PY =="
"$PY" - <<'PREFLIGHT'
import importlib
import sys

# A REAL import, never importlib.util.find_spec: find_spec only proves the
# package's files are on the path, so jsonschema with its own dependency (attrs)
# missing passed this preflight and then failed ten tests deep with
# "No module named attrs". The Skill 79 validator is loaded too, because it is
# the thing that actually needs jsonschema.
try:
    importlib.import_module("jsonschema")
    from launcher_core import checkout
    if checkout._load_validator() is None:
        raise ImportError("the Skill 79 validator (scripts/validate_checkout.py) was not found")
except Exception as exc:
    raise SystemExit(
        "verify: the Skill 79 checkout validator cannot load under %s (%s: %s). "
        "Install the runtime requirement into THIS interpreter first: "
        "%s -m pip install -r requirements.txt"
        % (sys.executable, type(exc).__name__, exc, sys.executable))
print("dependency-complete interpreter:", sys.executable)
print("runtime requirement importable: jsonschema (and the Skill 79 validator loads)")
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
