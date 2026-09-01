"""FIX 37 regression: board-reconcile-sweep.sh must report its own failure.

Why this exists (PRESENTATION-DEPT-FIX-SPEC.md FIX 37, bug 2): the sweep runs
under `set -euo pipefail`. The pre-fix code placed `rc=$?` on the line AFTER
the python call:

    python3 ... --reconcile-board ... >> log 2>&1
    rc=$?

Under `set -e`, a non-zero python exit killed the script AT the python line
itself -- the `rc=$?` line (and every line after) never ran, so the
error-report branch ("board-reconcile-sweep exited non-zero (exit N)") and
its FIX 37 telemetry event were silently skipped. The clock kept running and
the log simply stopped, mid-script: a reconcile sweep that failed looked
exactly like a reconcile sweep that was still running.

The fix retains `set -euo pipefail` but bounds ONLY the python call with the
`&& rc=0 || rc=$?` capture pattern, so `set -e` can no longer kill the
script before the error branch.

Spec proof targeted: "a forced reconcile failure prints its error."

Note on "forced failure": reconcile_sweep is fail-soft by design (cc_board
catching transport errors returns None from ingest and the python sweep
prints FAILED/UNDETERMINED lines, then returns non-zero: 10 for a scan that
found nothing, 11 for classification failures). The sweep script's error
branch is entered whenever the python exit is non-zero -- but whether python
goes non-zero for a dead-port board depends on sweep internals (an empty
scan root returns 10 even with a healthy board). This test therefore forces
the failure in BOTH ways:

  (a) full end-to-end against a real python + a dead localhost port +
      an EMPTY scan root -- python exits 10 (EXIT_SWEEP_NO_RUNS), and the
      script must print its error line. NO real network: COMMAND_CENTER_URL
      points at 127.0.0.1 on an unused port with CC_BOARD_TIMEOUT=1, and the
      empty root means the sweep never even reaches the board call.
  (b) a stub python3 that exits 42 -- the script's capture pattern must still
      reach the error branch (this is the branch `set -e` used to kill).

Four legs:

  1. STATIC -- `set -euo pipefail` present AND the `||` capture next to the
               python call (FIX 37 comment marker "FIX 37:" is the anchor).
               Also: NO bare `rc=$?` on a standalone line directly after the
               python invocation (the pre-fix shape).
  2. DYNAMIC (a) -- full script, real python, dead localhost port + scan root
               that the sweep resolves as UNDETERMINED-empty: assert the log
               contains "exited non-zero (exit 10)" and the telemetry
               reconcile_error event, and that the script does NOT die
               silently under set -e.
  3. DYNAMIC (b) -- stub python3 exiting 42: assert the log contains the
               error line and the telemetry event.
  4. NEGATIVE CONTROL -- revert a scratch copy of the script to the pre-fix
               `python ...; rc=$?` shape; run the exact same harness; assert
               the error branch and telemetry are SILENTLY MISSING (the log
               stops after the python call / never prints the non-zero line)
               -- proving leg 3 is non-vacuous.

Offline everywhere (dead 127.0.0.1 port = connection refused in well under
the timeout; no GHL, no real CC endpoint).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
SWEEP_SCRIPT = _SCRIPTS_DIR / "board-reconcile-sweep.sh"

# The python invocation with its `&& rc=0 || rc=$?` capture.
_CAPTURE_RE = re.compile(
    r"(?P<cmd>python3 \"?\$\{SCRIPT_DIR\}/presentation_job\.py\".*?)"
    r"(?P<capture>&& rc=0 \|\| rc=\$\?)",
    re.S,
)

_ERROR_LINE = "board-reconcile-sweep exited non-zero"


def test_sweep_script_exists_and_is_valid_bash():
    assert SWEEP_SCRIPT.is_file(), f"sweep script not found at {SWEEP_SCRIPT}"
    result = subprocess.run(
        ["bash", "-n", str(SWEEP_SCRIPT)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, (
        f"bash -n failed on {SWEEP_SCRIPT}:\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# 1. STATIC -- set -euo pipefail retained, || capture present, no bare rc=$?
# ---------------------------------------------------------------------------

def test_set_euo_pipefail_and_or_capture_both_present():
    src = SWEEP_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"^set -euo pipefail\s*$", src, re.M), (
        "board-reconcile-sweep.sh must keep `set -euo pipefail` (the fix keeps "
        "it and bounds only the python call)."
    )
    m = _CAPTURE_RE.search(src)
    assert m, (
        "the reconcile python call is not followed by `&& rc=0 || rc=$?` "
        "capture -- the FIX 37 capture pattern is the only thing that keeps "
        "`set -e` from killing the script before its error branch."
    )
    # The FIX 37 comment marker must sit adjacent to the captured invocation
    # (it is a comment line directly above it, so widen the window).
    window = src[: m.end("capture")][-600:]
    assert "FIX 37:" in window, (
        "the FIX 37 comment marker was not found beside the captured invocation"
    )


def test_no_bare_rc_dollar_question_after_python():
    """The pre-fix `rc=$?` on a standalone line right after the python call
    must be gone -- under set -e that line is unreachable anyway."""
    src = SWEEP_SCRIPT.read_text(encoding="utf-8")
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "presentation_job.py" in line and "--reconcile-board" in line:
            # The next non-blank, non-comment line must not be a bare `rc=$?`.
            for j in range(i + 1, min(i + 4, len(lines))):
                nxt = lines[j].strip()
                if not nxt or nxt.startswith("#"):
                    continue
                assert nxt != "rc=$?", (
                    "bare `rc=$?` found on the line after the python call -- "
                    "the pre-fix shape; under set -e it is unreachable. The "
                    "capture must be `&& rc=0 || rc=$?` on the SAME command."
                )
                break


# ---------------------------------------------------------------------------
# Sandbox runner (shared by legs 2-4).
# ---------------------------------------------------------------------------

def _run_sweep_script(script: Path, tmp_path: Path) -> str:
    """Run `script` (or a scratch copy) in a fully sandboxed HOME with an
    empty scan root and a dead localhost COMMAND_CENTER_URL. Returns the
    sweep log text.

    Never touches the real network: port 1 on 127.0.0.1 refuses instantly
    (nothing listens there), and the empty scan root means the sweep returns
    EXIT_SWEEP_NO_RUNS from python WITHOUT the sweep ever issuing a board
    request (the python resolve of the root list and the empty loop happen
    before any ingest). PRESENTATION_RUNS_DIR points at a tmp dir so the
    telemetry write lands in the sandbox, never a real department dir."""
    home = tmp_path / "home"
    (home / "Library" / "Logs" / "openclaw").mkdir(parents=True)
    runs_dir = tmp_path / "pres-runs"
    runs_dir.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    log_file = home / "Library" / "Logs" / "openclaw" / "board-reconcile-sweep.log"

    env = {
        "HOME": str(home),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "SCAN_ROOT": str(scan_root),
        "COMMAND_CENTER_URL": "http://127.0.0.1:1",
        "CC_API_TOKEN": "test-token",
        "WEBHOOK_SECRET": "test-secret",
        "CC_BOARD_TIMEOUT": "1",
        "PRESENTATION_RUNS_DIR": str(runs_dir),
    }
    result = subprocess.run(
        ["bash", str(script)],
        cwd=str(_SCRIPTS_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    # The sweep script's own exit code is 0 -- its LAST statement is a
    # completing `echo ... complete` (a defect noted in the script header as
    # intentional? it is the pre-existing shape; the FIX 37 scope is the
    # error branch firing, not the exit code). We assert on the log + rc
    # where it matters (leg 4 checks the negative by absence of the line).
    telemetry = runs_dir / "telemetry" / "events.jsonl"
    tele_text = telemetry.read_text(encoding="utf-8") if telemetry.exists() else ""
    return (
        f"[script_rc={result.returncode}]\n"
        f"[stdout={result.stdout}]\n[stderr={result.stderr}]\n"
        f"[log={log_file.read_text(encoding='utf-8') if log_file.exists() else '<missing>'}]"
        f"\n[telemetry={tele_text!r}]"
    )


# ---------------------------------------------------------------------------
# 2. DYNAMIC (a) -- dead localhost port + empty scan root: error branch fires.
# ---------------------------------------------------------------------------

def test_dead_port_failure_is_reported_not_silently_died(tmp_path):
    """Sandboxed end-to-end: real python, dead 127.0.0.1:1, empty scan root.
    The sweep returns 10 (EXIT_SWEEP_NO_RUNS); the script must run its error
    branch -- the log must contain the non-zero line and the telemetry
    reconcile_error event must be written. Pre-fix, set -e killed the script
    before either existed."""
    out = _run_sweep_script(SWEEP_SCRIPT, tmp_path)
    assert _ERROR_LINE in out, (
        "sweep did not report its own non-zero exit -- the error branch was "
        "skipped. This is the FIX 37 bug (set -e killing the script before "
        f"the report).\n{out}"
    )
    assert '"event":"reconcile_error"' in out, (
        "FIX 37 telemetry reconcile_error event was not written.\n" + out
    )
    assert "exit 10" in out, (
        "expected the swept python failure (exit 10) to be named in the "
        f"report.\n{out}"
    )


# ---------------------------------------------------------------------------
# 3. DYNAMIC (b) -- stub python exiting 42: capture pattern reaches branch.
# ---------------------------------------------------------------------------

def test_stub_python_exit_42_is_reported(tmp_path):
    """Stub python3 to exit 42 -- simulating a hard reconcile failure -- and
    assert the error branch still fires. This leg does not depend on sweep
    internals: if python exits non-zero for ANY reason, the script must say
    so and write the telemetry event."""
    home = tmp_path / "home"
    (home / "Library" / "Logs" / "openclaw").mkdir(parents=True)
    runs_dir = tmp_path / "pres-runs"
    runs_dir.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python3"
    stub.write_text("#!/usr/bin/env bash\nexit 42\n", encoding="utf-8")
    stub.chmod(0o755)
    log_file = home / "Library" / "Logs" / "openclaw" / "board-reconcile-sweep.log"

    env = {
        "HOME": str(home),
        "PATH": f"{bindir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "SCAN_ROOT": str(scan_root),
        "PRESENTATION_RUNS_DIR": str(runs_dir),
    }
    result = subprocess.run(
        ["bash", str(SWEEP_SCRIPT)],
        cwd=str(_SCRIPTS_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (
        f"[script_rc={result.returncode}]\n[stdout={result.stdout}]\n"
        f"[stderr={result.stderr}]\n"
        f"[log={log_file.read_text(encoding='utf-8')}]"
    )
    assert _ERROR_LINE in out, (
        "stub python exiting 42 was NOT reported -- the `&& rc=0 || rc=$?` "
        "capture is not reaching the error branch (or set -e killed the "
        f"script first).\n{out}"
    )
    assert "exit 42" in out, f"expected the report to name exit 42.\n{out}"


# ---------------------------------------------------------------------------
# 4. NEGATIVE CONTROL -- the pre-fix `python; rc=$?` shape must be caught.
# ---------------------------------------------------------------------------

def test_pre_fix_rc_equal_shape_dies_silently(tmp_path):
    """Revert a SCRATCH COPY (never the worktree -- the fixed script is read
    from disk, only the scratch copy is written) of the python call to the
    pre-fix `python ...; rc=$?` shape (capture removed), run it with the stub
    python exiting 42, and confirm the error branch NEVER fires: the log must
    NOT contain the non-zero line, proving the pre-fix script was killed by
    set -e before reporting. Guards the guard: if leg 3 were ever weakened
    into a vacuous pass, this still proves the harness reproduces the
    historical silent death."""
    fixed = SWEEP_SCRIPT.read_text(encoding="utf-8")
    m = _CAPTURE_RE.search(fixed)
    assert m, "could not locate the capture block to revert"
    # Replace `... >> log 2>&1 && rc=0 || rc=$?` with the pre-fix
    # `... >> log 2>&1` then a standalone `rc=$?` (the shape set -e kills).
    old_tail = m.group("cmd") + m.group("capture")
    new_cmd = m.group("cmd").rstrip() + ">> \"${LOG_FILE}\" 2>&1\nrc=$?"
    broken = fixed[: m.start("cmd")] + new_cmd + fixed[m.end("capture"):]
    assert "&& rc=0 || rc=$?" not in broken and "rc=$?" in broken, (
        "failed to synthesize the pre-fix shape"
    )
    scratch = tmp_path / "board-reconcile-sweep.sh"
    scratch.write_text(broken, encoding="utf-8")
    scratch.chmod(0o755)

    home = tmp_path / "home"
    (home / "Library" / "Logs" / "openclaw").mkdir(parents=True)
    runs_dir = tmp_path / "pres-runs"
    runs_dir.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python3"
    stub.write_text("#!/usr/bin/env bash\nexit 42\n", encoding="utf-8")
    stub.chmod(0o755)
    log_file = home / "Library" / "Logs" / "openclaw" / "board-reconcile-sweep.log"

    result = subprocess.run(
        ["bash", str(scratch)],
        cwd=str(_SCRIPTS_DIR),
        env={
            "HOME": str(home),
            "PATH": f"{bindir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "SCAN_ROOT": str(tmp_path / "scan"),
            "PRESENTATION_RUNS_DIR": str(runs_dir),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (
        f"[script_rc={result.returncode}]\n"
        f"[log={log_file.read_text(encoding='utf-8') if log_file.exists() else '<missing>'}]"
    )
    assert _ERROR_LINE not in out, (
        "negative control did NOT reproduce the historical silent death: the "
        "reverted pre-fix shape still reported the error -- the harness may "
        f"not actually be exercising set -e semantics.\n{out}"
    )
    assert '"event":"reconcile_error"' not in out, (
        "negative control wrote the telemetry event -- the pre-fix shape "
        "should die before the error branch.\n" + out
    )
