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
    from launcher_core import checkout  # first: importing the package puts the shared pydeps folder on sys.path
    importlib.import_module("jsonschema")
    if checkout._load_validator() is None:
        raise ImportError("the Skill 79 validator (scripts/validate_checkout.py) was not found")
except Exception as exc:
    raise SystemExit(
        "verify: the Skill 79 checkout validator cannot load under %s (%s: %s). "
        "Install the runtime requirement first (never --break-system-packages, never a venv): "
        "%s -m launcher_core.cli dependencies --install"
        % (sys.executable, type(exc).__name__, exc, sys.executable))
print("dependency-complete interpreter:", sys.executable)
print("runtime requirement importable: jsonschema (and the Skill 79 validator loads)")
PREFLIGHT

echo "== open and decided seams =="
"$PY" -m launcher_core.cli seams

# unittest never loads conftest.py, so the offline GHL read-back that every TEST-ONLY fixture needs (PRD-12)
# is installed here, exactly as conftest.py installs it for pytest: once before any setUpClass, and again
# around every test (test_entitlement_readback resets the seam itself). Fixtures name TEST-ONLY references
# only; the transport resolves those and nothing else, and no test is skipped.
# The unittest runner is BOUNDED. Eight client boxes had to find and SIGTERM a
# spinning runner by hand because this script had no ceiling.
# The bound is a background job plus a watchdog, deliberately not timeout(1):
# on macOS coreutils timeout exists only via Homebrew, and under a clean
# /usr/bin:/bin:/usr/sbin:/sbin PATH neither `timeout` nor `gtimeout` resolves
# (measured), so relying on it would bound the operator box and hang every other
# one. perl is the same kind of "usually there" bet. The shell is always present.
# The watchdog writes an explicit marker only when it actually delivered the
# TERM, so exit 124 means exactly "the bound fired" and a stray SIGKILL (an OOM
# kill, say) keeps its own status instead of being misreported as a timeout.
# A healthy stage-1 discovery measured 633 s on a quiet Mac Mini and 807.881 s
# on the same box under load (Ran 657 tests), so the bound has to clear the SLOW
# end by a real margin: 1800 s is 2.2x the contended measurement. Anything near
# the quiet number would convert a passing but busy box into a false timeout.
# UNIT_TIMEOUT=<seconds> moves the bound without editing this file.
UNIT_TIMEOUT="${UNIT_TIMEOUT:-1800}"
case "$UNIT_TIMEOUT" in
    '' | *[!0-9]*) echo "verify: UNIT_TIMEOUT must be whole seconds, got '$UNIT_TIMEOUT'" >&2; exit 1 ;;
esac

run_unittest() {
    local mark pid wd rc=0 waited=0
    mark="$(mktemp "${TMPDIR:-/tmp}/bf83-unit.XXXXXX")" || return 1
    "$PY" - "$HERE" "$@" <<'RUNNER' &
import sys
import unittest

here, argv = sys.argv[1], sys.argv[2:]
sys.path[:0] = [here, here + "/fixtures"]
from launcher_core import entitlement
from test_only_readback import test_only_transport

entitlement.set_transport(test_only_transport())
_run = unittest.TestCase.run


def run(self, result=None):
    entitlement.set_transport(test_only_transport())
    try:
        return _run(self, result)
    finally:
        entitlement.set_transport(test_only_transport())


unittest.TestCase.run = run
unittest.main(module=None, argv=["unittest", "discover", *argv], exit=True)
RUNNER
    pid=$!
    # ponytail: this kills one pid, not a process group, so a stuck GRANDCHILD
    # of the runner would survive. The reported spinner was the top-level runner
    # itself (faulthandler stack), so one pid is enough; add `set -m` plus
    # `kill -TERM -- -$pid` if a grandchild ever turns out to spin.
    ( while [ "$waited" -lt "$UNIT_TIMEOUT" ] && kill -0 "$pid" 2>/dev/null; do
          sleep 1; waited=$((waited + 1))
      done
      # The runner finished on its own: nothing to bound.
      kill -0 "$pid" 2>/dev/null || exit 0
      printf 'timed out\n' >"$mark"
      kill -TERM "$pid" 2>/dev/null || true
      sleep 5
      kill -KILL "$pid" 2>/dev/null || true ) &
    wd=$!

    # A genuinely failing test still returns unittest's own status here, and a
    # crash keeps its own status; only the marker path returns 124.
    wait "$pid" || rc=$?
    kill "$wd" 2>/dev/null || true
    wait "$wd" 2>/dev/null || true

    if [ -s "$mark" ]; then
        echo "verify: the unittest runner exceeded UNIT_TIMEOUT=${UNIT_TIMEOUT}s and was killed" >&2
        rm -f "$mark"
        return 124
    fi
    rm -f "$mark"
    return "$rc"
}

echo "== unit + integration checks =="
run_unittest -s tests -p 'test_*.py' -v

echo "== route invariants, adapter wiring and the offline browser diagnostic =="
# BrowserDiagnosticTests lives in this file and runs here exactly once, through
# discovery. It probes this machine for browser tooling, prints exactly what it
# found, and proves the landing -> checkout route wiring and the Skill 79 order
# form binding without driving a browser; a failure fails this script.
run_unittest -s "$HERE/routes/tests" -p 'test_routes.py' -v

echo "== worked-example fixtures =="
"$PY" "$HERE/fixtures/run_fixtures.py"

echo "== 999 dependency package =="
"$PY" -m launcher_core.cli dependencies
