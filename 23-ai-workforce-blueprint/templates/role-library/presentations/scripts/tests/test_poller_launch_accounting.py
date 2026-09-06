"""Regression: presentation-intake-poll.sh must NEVER report a refused
dispatch as a launch.

WHY THIS EXISTS (measured on the operator Mac, 2026-09-06). On a pass where
the launcher printed, twice:

    launcher: REFUSING to dispatch <run> -- AF-NOTIFY-UNCONFIGURED:
    PRESENTATION_NOTIFY_CMD is unset or blank ...

the poller's own summary line said:

    scan complete: 2 launched

No engine had started. The counter was incremented unconditionally after the
dispatch pipeline, so it counted ATTEMPTS, not SUCCESSES -- and the only line
an operator reads said the pipeline was working while it had in fact been
dead on arrival every five minutes for over a day. A run could appear
started and never have started. That is the defect this file pins.

The root cause is a shell subtlety worth naming, because it is easy to
reintroduce: every dispatch is piped into the log loop

    ( ... launcher ... ) 2>&1 | while IFS= read -r line; do log "  $line"; done

and `$?` after that pipeline is the WHILE LOOP's status, which is always 0.
The launcher's own status is ${PIPESTATUS[0]}. Reading `$?` there -- or not
reading a status at all -- is what made the refusal invisible.

FOUR LEGS, mirroring tests/test_fix37_poller_counter.py's discipline:

  1. STATIC   -- every NEW_LAUNCHES increment is guarded by a dispatch-status
                 check, and a status is actually captured from PIPESTATUS
                 after each dispatch pipeline.
  2. DYNAMIC  -- extract the poller's walk-loop body VERBATIM from the
                 shipped script and EXECUTE it against a scratch run dir,
                 with `python3` stubbed to a launcher that REFUSES exactly
                 the way the real one did (prints the AF-NOTIFY-UNCONFIGURED
                 line, exits 8). The summary must say 0 launched / 1 refused.
  3. NEGATIVE CONTROL -- rebuild the SAME harness with the increment reverted
                 to the pre-fix unconditional form. The identical refusal
                 must then be reported as "1 launched", proving leg 2 is not
                 a vacuous pass but actually catches the historical bug.
  4. POSITIVE CONTROL -- the same harness with a launcher stub that SUCCEEDS
                 must report 1 launched / 0 refused, proving the counter has
                 not simply been nailed to zero.

Legs 3 and 4 together are the control pair the negative-result contract
requires: leg 2's "0 launched" is only meaningful because leg 4 proves the
same harness can produce "1 launched", and leg 3 proves the pre-fix shape
still produces the wrong answer.

Every leg is offline. The stub `python3` never imports the package, never
spawns an engine, never touches the network; the lease is disabled through
its own documented rollback (PRESENTATION_INTAKE_LEASE=0) so no lease file
is written. Scratch dirs are pytest tmp_path fixtures.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
POLL_SCRIPT = _SCRIPTS_DIR / "presentation-intake-poll.sh"

# Same anchored walk-loop extraction test_fix37_poller_counter.py uses: the
# `done < <(find` close is what stops the non-greedy body at the REAL loop
# close rather than at an inner `done` of a log-piping `| while`.
_WALK_RE = re.compile(
    r"while IFS= read -r run_dir;\s*do(?P<body>.*?)done\s*<\s*<\(find",
    re.S,
)

# The exact refusal the real launcher emits when notify_gate fails closed
# (presentation_job/notify_preflight.py: AF_NOTIFY_UNCONFIGURED, and
# launcher.py's `REFUSING to dispatch` line). EXIT_NOTIFY_UNCONFIGURED = 8.
_AF_LINE = ("launcher: REFUSING to dispatch RUNDIR -- AF-NOTIFY-UNCONFIGURED: "
            "PRESENTATION_NOTIFY_CMD is unset or blank")

#: A `python3` stand-in. `-c` (the poller's ledger/terminal/pid probes) must
#: print NOTHING and exit 0, which the poller reads as "intake complete, not
#: terminal, no live pid" -- the resume-branch condition. The launcher module
#: invocation is what each leg varies.
_STUB = """#!/usr/bin/env bash
if [ "$1" = "-c" ]; then exit 0; fi
case " $* " in
  *" -m presentation_job.launcher "*)
    {LAUNCHER_BODY}
    ;;
esac
exit 0
"""

_REFUSING_LAUNCHER = f'echo "{_AF_LINE}"\n    exit 8'
_SUCCEEDING_LAUNCHER = 'echo "launcher: dispatched (stub)"\n    exit 0'


def _extract_walk_body(src: str) -> str:
    m = _WALK_RE.search(src)
    assert m, (
        "could not find the poller's `while ... done < <(find ...)` walk loop "
        "-- has its shape changed?"
    )
    return m.group("body").rstrip("\n")


def _make_parked_run(runs_root: Path, name: str) -> Path:
    """A run dir in the poller's RESUME condition: completed intake ledger,
    a state.json that is NOT terminal and names no live pid."""
    run_dir = runs_root / f"pres-{name}"
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({
            "status": "complete",
            "complete": True,
            "entries": {"presentation_type": {"value": "from_scratch"}},
        }),
        encoding="utf-8",
    )
    (run_dir / "state.json").write_text(
        json.dumps({"schema_version": 1, "job_id": "pj_test", "terminal": ""}),
        encoding="utf-8",
    )
    return run_dir


def _run_harness(body: str, tmp_path: Path, launcher_body: str,
                 pre_fix: bool = False) -> str:
    """Execute the poller's OWN walk-loop body against one parked run dir.

    `pre_fix=True` rewrites the guarded increment back to the historical
    unconditional form -- on a SCRATCH COPY of the extracted body, never on
    the worktree file -- so leg 3 can prove the harness catches the real bug.
    """
    if pre_fix:
        # The historical shape: increment no matter what the launcher did.
        body = re.sub(
            r"DISPATCH_RC=\$\{PIPESTATUS\[0\]\}.*?\n        fi\n",
            "NEW_LAUNCHES=$((NEW_LAUNCHES + 1))\n",
            body,
            count=1,
            flags=re.S,
        )
        assert "DISPATCH_RC" not in body, (
            "the pre-fix rewrite did not remove the guarded increment -- the "
            "negative control would be testing the fixed shape and pass "
            "vacuously"
        )

    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python3"
    stub.write_text(_STUB.replace("{LAUNCHER_BODY}", launcher_body),
                    encoding="utf-8")
    stub.chmod(0o755)

    runs_root = tmp_path / "runs"
    _make_parked_run(runs_root, "alpha")
    log_file = tmp_path / "poll.log"

    harness = "\n".join([
        "set -uo pipefail",
        f'export PATH="{bindir}:$PATH"',
        "PROG=presentation-intake-poll.sh",
        f'LOG_FILE="{log_file}"',
        "log() {",
        '    echo "$(date \'+%Y-%m-%dT%H:%M:%S%z\') [$PROG] $*" >> "$LOG_FILE"',
        "}",
        # read_run_mode is stubbed to "undeclared" (the launcher default
        # applies) so this test exercises accounting, not mode routing.
        "read_run_mode() { :; }",
        f'RUNS_ROOT="{runs_root}"',
        f'SCRIPTS_DIR="{_SCRIPTS_DIR}"',
        f'ENGINE_ENTRY="{_SCRIPTS_DIR / "presentation_job.py"}"',
        f'LAUNCHER="{_SCRIPTS_DIR / "presentation_job" / "launcher.py"}"',
        # PRESENTATION_INTAKE_LEASE=0 is the poller's own documented rollback:
        # no lease file is written and the lease helpers are never called.
        'LEASE_ENABLED="0"',
        "NEW_LAUNCHES=0",
        "REFUSED_DISPATCH=0",
        "SKIPPED_RUNNING=0",
        "SKIPPED_NO_INTAKE=0",
        "SKIPPED_TERMINAL=0",
        "SKIPPED_LEASE_HELD=0",
        "LEASE_TAKEOVERS=0",
        "RUN_DIRS_SEEN=0",
        'RUN_MODE=""',
        "while IFS= read -r run_dir; do",
        body,
        'done < <(find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" 2>/dev/null)',
        'log "scan complete: $NEW_LAUNCHES launched, $REFUSED_DISPATCH refused"',
        "",
    ])
    result = subprocess.run(["bash", "-c", harness], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, (
        "the accounting harness itself failed -- a harness that aborts proves "
        "nothing about the counter (this is exactly how a control goes "
        f"vacuous).\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return log_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. STATIC
# ---------------------------------------------------------------------------

def test_every_launch_increment_is_guarded_by_a_dispatch_status():
    """No NEW_LAUNCHES increment may sit unguarded after a dispatch. Each one
    must be inside a branch that tested a captured dispatch exit status."""
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    lines = src.splitlines()
    increments = [i for i, l in enumerate(lines)
                  if "NEW_LAUNCHES=$((NEW_LAUNCHES + 1))" in l]
    assert increments, "no NEW_LAUNCHES increment found at all"
    for idx in increments:
        window = "\n".join(lines[max(0, idx - 6):idx])
        assert re.search(r'if \[ "\$(DISPATCH_RC|CREATE_RC|RUN_RC)" -eq 0 \]',
                         window), (
            "a NEW_LAUNCHES increment is not guarded by a dispatch-status "
            f"check; the six lines above line {idx + 1} are:\n{window}\n"
            "An unguarded increment counts a REFUSAL as a LAUNCH."
        )


def test_dispatch_status_is_read_from_pipestatus_not_dollar_question():
    """Every dispatch is piped into the log loop, so `$?` is the LOOP's
    status (always 0). The launcher's own status is ${PIPESTATUS[0]}."""
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    for var in ("DISPATCH_RC", "CREATE_RC", "RUN_RC"):
        assert f"{var}=${{PIPESTATUS[0]}}" in src, (
            f"{var} is not captured from ${{PIPESTATUS[0]}}. Reading `$?` "
            "after a `| while` pipeline yields the loop's status, never the "
            "dispatching command's -- that is the original defect."
        )


def test_no_continue_in_the_walk_loop_is_silent():
    """Every `continue` in the run-dir walk ends the poller's handling of one
    run dir, so every one of them must increment SOME counter. A `continue`
    that counts nothing is a run dir that vanished from the accounting -- the
    same class of lie as counting a refusal as a launch, just quieter. One
    such path existed (the resolve_intake failure branch): a dispatch that
    produced no engine, invisible in the summary AND in the telemetry event,
    on the exact path the script's own comment describes as retrying "the
    identical failure every 5 minutes, forever"."""
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    body = _extract_walk_body(src)
    lines = body.splitlines()
    counters = ("SKIPPED_NO_INTAKE", "SKIPPED_TERMINAL", "SKIPPED_RUNNING",
                "SKIPPED_LEASE_HELD", "REFUSED_DISPATCH", "NEW_LAUNCHES")
    silent = []
    for i, line in enumerate(lines):
        if line.strip() != "continue":
            continue
        window = "\n".join(lines[max(0, i - 8):i])
        if not any(f"{c}=$((" in window for c in counters):
            silent.append(i)
    assert not silent, (
        "a `continue` in the walk loop increments no counter, so the run dir "
        "it abandons is reported nowhere:\n"
        + "\n".join("..." + "\n".join(lines[max(0, i - 8):i + 1])
                    for i in silent)
    )


def test_run_dirs_seen_makes_the_accounting_tally():
    """RUN_DIRS_SEEN is incremented once per run dir, so an operator can check
    seen == launched + refused + every skip. Without it an under-count is
    invisible; with it, it is arithmetic."""
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    body = _extract_walk_body(src)
    assert body.count("RUN_DIRS_SEEN=$((RUN_DIRS_SEEN + 1))") == 1, (
        "RUN_DIRS_SEEN must be incremented exactly once per run dir"
    )
    assert '"run_dirs_seen":%d' in src, (
        "run_dirs_seen is not in the poller_scan telemetry event, so the "
        "tally cannot be checked by a consumer"
    )


def test_summary_line_and_telemetry_report_refusals():
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    assert "$REFUSED_DISPATCH refused" in src, (
        "the scan-complete summary line does not report refusals -- an "
        "operator reading it cannot tell a dead pipeline from a working one"
    )
    assert '"refused":%d' in src, (
        "the poller_scan telemetry event carries no `refused` field"
    )
    # The pre-existing FIX 37 guard pins this exact substring; keep it.
    assert "scan complete: $NEW_LAUNCHES launched" in src


# ---------------------------------------------------------------------------
# 2. DYNAMIC -- the real proof.
# ---------------------------------------------------------------------------

def test_refused_dispatch_is_not_counted_as_a_launch(tmp_path):
    """Run the poller's OWN loop body against a parked run dir with a
    launcher stub that refuses exactly as the real one did. The summary must
    say 0 launched and 1 refused, and the refusal must be visible in the
    log."""
    body = _extract_walk_body(POLL_SCRIPT.read_text(encoding="utf-8"))
    log_text = _run_harness(body, tmp_path, _REFUSING_LAUNCHER)

    assert "AF-NOTIFY-UNCONFIGURED" in log_text, (
        "the launcher's refusal never reached the log -- the harness is not "
        "exercising the dispatch path:\n" + log_text
    )
    assert "scan complete: 0 launched, 1 refused" in log_text, (
        "a REFUSED dispatch was counted as a launch (or not counted at all). "
        "Log:\n" + log_text
    )
    assert "NOT LAUNCHED" in log_text, (
        "the poller did not say out loud that nothing was launched:\n" + log_text
    )


# ---------------------------------------------------------------------------
# 3. NEGATIVE CONTROL -- the pre-fix shape must be caught.
# ---------------------------------------------------------------------------

def test_prefix_unconditional_increment_would_have_lied(tmp_path):
    """The SAME harness, with the increment reverted to the historical
    unconditional form on a scratch copy of the body, must report the SAME
    refusal as "1 launched". That is the bug this file exists to prevent, and
    proving the harness still reproduces it is what makes leg 2 non-vacuous."""
    body = _extract_walk_body(POLL_SCRIPT.read_text(encoding="utf-8"))
    log_text = _run_harness(body, tmp_path, _REFUSING_LAUNCHER, pre_fix=True)

    assert "AF-NOTIFY-UNCONFIGURED" in log_text, (
        "the negative control did not even reach the dispatch:\n" + log_text
    )
    assert "scan complete: 1 launched" in log_text, (
        "the negative control did NOT reproduce the historical lie, so the "
        "dynamic leg above may be passing for the wrong reason. Log:\n"
        + log_text
    )


# ---------------------------------------------------------------------------
# 4. POSITIVE CONTROL -- the counter is not simply nailed to zero.
# ---------------------------------------------------------------------------

def test_successful_dispatch_is_counted_as_a_launch(tmp_path):
    """A launcher that EXITS 0 must be counted. Without this leg, "0
    launched" above would also be satisfied by a counter that can never
    increment -- the class of broken check the negative-result contract
    warns about."""
    body = _extract_walk_body(POLL_SCRIPT.read_text(encoding="utf-8"))
    log_text = _run_harness(body, tmp_path, _SUCCEEDING_LAUNCHER)

    assert "scan complete: 1 launched, 0 refused" in log_text, (
        "a SUCCESSFUL dispatch was not counted as a launch -- the counter may "
        "be nailed to zero. Log:\n" + log_text
    )
