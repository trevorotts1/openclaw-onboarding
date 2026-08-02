#!/usr/bin/env python3
"""test_subprocess_timeout.py -- Prove every subprocess.call/run call in the
anthology-engine scripts has a timeout= bound, and that a sleeping child process
is reliably interrupted and the parent returns within the bound.

QC: F24/E18 subprocess-no-timeout scan -> 0 hits; pytest stays green; a
sleeping-child unit test proves the parent returns within the bound.

Run: python3 -m pytest 59-anthology-engine/tests/test_subprocess_timeout.py -q
"""
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_sleeping_child_terminated_by_timeout():
    """A subprocess that sleeps 999s must be killed by the timeout (raises
    TimeoutExpired) and the parent must return before 999s.

    This mirrors the fail-soft pattern used in the production scripts:
    the TimeoutExpired is caught and the caller proceeds."""
    start = time.monotonic()
    try:
        subprocess.call(
            [sys.executable, "-c", "import time; time.sleep(999)"],
            timeout=2)
    except subprocess.TimeoutExpired:
        pass
    elapsed = time.monotonic() - start
    assert elapsed < 10, (
        "parent must return within the bound after catching TimeoutExpired; "
        "elapsed %.2fs, but a sleeping child was wedged" % elapsed)


def test_all_script_subprocess_calls_have_timeout():
    """Prove zero subprocess.call/run calls in the script set are missing
    timeout=."""
    import re
    script_files = [
        "model_router.py",
        "anthology_book.py",
        "pdf_render.py",
        "qc-tier1-anthology.py",
        "qc-strike-gate.py",
    ]
    missing = []
    for sf in script_files:
        path = SCRIPTS / sf
        if not path.is_file():
            missing.append("%s: file not found" % sf)
            continue
        content = path.read_text()
        call_sites = list(re.finditer(
            r'subprocess\.(?:call|run)\(', content))
        timeout_sites = list(re.finditer(
            r'subprocess\.(?:call|run)\(.+?timeout=', content, re.DOTALL))
        if len(call_sites) != len(timeout_sites):
            missing.append(
                "%s: %d subprocess calls, %d have timeout=" %
                (sf, len(call_sites), len(timeout_sites)))

    assert not missing, (
        "subprocess-no-timeout scan found hits:\n" +
        "\n".join(missing))


def test_sleeping_child_returns_within_bound_across_boundaries():
    """Vary the timeout value and prove the parent returns in <= timeout+2s
    across a range of bounds."""
    for timeout_s in (1, 3, 5):
        start = time.monotonic()
        try:
            subprocess.call(
                [sys.executable, "-c", "import time; time.sleep(999)"],
                timeout=timeout_s)
        except subprocess.TimeoutExpired:
            pass
        elapsed = time.monotonic() - start
        assert elapsed < timeout_s + 2, (
            "parent must return within timeout+2s; "
            "timeout=%ds, elapsed=%.2fs" % (timeout_s, elapsed))
