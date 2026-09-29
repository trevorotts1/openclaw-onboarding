"""Fix 2 (C3) — the poller can never install a self-executing interpreter shim.

The defect: when pipeline_interp resolution failed, `_pres35_finish_interpreter()`
in presentation-intake-poll.sh fell back to the bare name `_resolved="python3"`,
then installed a PATH-front shim whose whole content was `exec "python3" "$@"`.
That is an infinite self-exec: the tick never finishes and intake stalls.

The fix: the fallback resolves via `command -v python3` (an absolute path), and a
guard refuses any non-absolute `_resolved` on every branch (schedule-pin
included) plus anything inside the shim dir, before the shim is written.

This test extracts `_pres35_finish_interpreter()` VERBATIM from the shipped
script and runs it in a sandbox where PRESENTATION_PY is unset and
pipeline_interp.py is absent. It asserts:
  1. the installed shim's python3 content starts with `exec "/` (absolute path),
  2. the tick finishes (the function returns 0),
  3. executing the shim actually runs a real interpreter instead of
     self-executing (under the old code this step recursed until timeout).

Unit-level: no network, no spend, no deck. The shim is executed once with
`python3 -c` under a timeout; nothing else is launched.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
POLLER = _SCRIPTS_DIR / "presentation-intake-poll.sh"


def _extract_finish_interpreter() -> str:
    src = POLLER.read_text()
    m = re.search(r"(?m)^_pres35_finish_interpreter\(\) \{$.*?^}$", src, re.S)
    assert m, "could not extract _pres35_finish_interpreter from the poll script"
    return m.group(0)


def test_fallback_installs_absolute_shim_and_tick_finishes(tmp_path):
    """PRESENTATION_PY unset + pipeline_interp.py absent: the shim must carry an
    absolute interpreter path and the tick must finish."""
    scripts_dir = tmp_path / "scripts"
    (scripts_dir / "presentation_job").mkdir(parents=True)
    # NOTE: presentation_job/pipeline_interp.py is deliberately ABSENT.
    runs = tmp_path / "runs"
    runs.mkdir()

    func = _extract_finish_interpreter()
    harness = (
        'log() { echo "LOG: $*"; }\n'
        f'SCRIPTS_DIR="{scripts_dir}"\n'
        f'RUNS_ROOT="{runs}"\n'
        "unset PRESENTATION_PY\n"
        "unset PRESENTATION_PIPELINE_INTERPRETER\n"
        + func
        + "\n_pres35_finish_interpreter\n"
        'echo "FUNC_RC=$?"\n'
    )
    py_dir = os.path.dirname(sys.executable)
    env = {
        **os.environ,
        "PATH": f"{py_dir}:/usr/bin:/bin",
    }
    res = subprocess.run(
        ["bash", "-c", harness],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "FUNC_RC=0" in res.stdout, (
        "the tick did not finish (function did not return 0):\n"
        + res.stdout
        + res.stderr
    )

    # Fix 36: the shim is the stable .interp-shim/python3, not per-PID.
    shims = list((runs / "working").glob(".interp-shim/python3"))
    assert len(shims) == 1, f"expected exactly one shim, found: {shims}"
    content = shims[0].read_text()
    lines = content.splitlines()
    assert len(lines) >= 2, f"shim content too short: {content!r}"
    assert lines[1].startswith('exec "/'), (
        "shim must exec an ABSOLUTE interpreter path, got: " + lines[1]
    )

    # The shim must be safe to execute: PATH-front, it must run the real
    # interpreter, not self-exec. Under the pre-fix code this recursed
    # until the timeout below.
    shim_dir = str(shims[0].parent)
    run = subprocess.run(
        [str(shims[0]), "-c", "import sys; print('shim-ok')"],
        env={**os.environ, "PATH": f"{shim_dir}:{os.environ.get('PATH', '')}"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "shim-ok" in run.stdout, run.stdout + run.stderr
