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
import sys
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

# F3 added helper functions the walk-loop body CALLS (file_mtime,
# verify_engine_running, engine_stderr_tail, ledger_sha256) plus the variables
# they read. The harness below extracts that block VERBATIM from the shipped
# script rather than re-stubbing it, for the same reason the body itself is
# extracted: a hand-written stand-in is a second implementation, and the one
# that ships is then never the one under test.
_HELPERS_RE = re.compile(
    r"# >>> POLLER-LAUNCH-VERIFY-BEGIN\n(?P<block>.*?)# <<< POLLER-LAUNCH-VERIFY-END",
    re.S,
)

# The exact refusal the real launcher emits when notify_gate fails closed
# (presentation_job/notify_preflight.py: AF_NOTIFY_UNCONFIGURED, and
# launcher.py's `REFUSING to dispatch` line). EXIT_NOTIFY_UNCONFIGURED = 8.
_AF_LINE = ("launcher: REFUSING to dispatch RUNDIR -- AF-NOTIFY-UNCONFIGURED: "
            "PRESENTATION_NOTIFY_CMD is unset or blank")

#: A `python3` stand-in. The poller's `-c` probes (intake complete, terminal,
#: engine pid) run on the REAL interpreter against the fixture's own files, so
#: a leg that sets `terminal="BLOCKED"` actually reaches the F1 branch instead
#: of being told "not terminal" by a stub that answers every question with
#: silence. The `--new` spawner (`-c` containing `subprocess`) stays stubbed:
#: that one would start an engine.
#:
#: This used to be a blanket `if [ "$1" = "-c" ]; then exit 0; fi`, which read
#: as "intake complete, not terminal, no live pid" for every fixture. That is
#: the same answer the real probes give for the non-terminal fixtures these
#: legs already used -- so nothing below changes shape -- but it made a
#: terminal fixture UNREPRESENTABLE, and a harness that cannot express the
#: state under test is a harness that passes for the wrong reason.
_STUB = """#!/usr/bin/env bash
REAL_PY={real_py}
if [ "$1" = "-c" ]; then
  case "$2" in
    *subprocess*) exit 0 ;;
    *) exec "$REAL_PY" "$@" ;;
  esac
fi
case " $* " in
  *" -m presentation_job.launcher "*)
    {LAUNCHER_BODY}
    ;;
  *" -m presentation_job.auto_resume "*)
    # F1's decider. Defaulted to 3 = "leave it parked", so a stub that returns
    # 0 for everything it does not recognise can never silently authorise a
    # resume; the one leg that needs a "yes" asks for it explicitly.
    exit {AUTO_RESUME_RC}
    ;;
esac
exit 0
"""

_REFUSING_LAUNCHER = f'echo "{_AF_LINE}"\n    exit 8'

#: A launcher stub that SUCCEEDS -- and, since F3, a stub that exits 0 while
#: leaving nothing running is no longer a successful launch, it is precisely
#: the historical lie (two one-second engine deaths reported as "2 launched").
#: So this stub leaves exactly the evidence a real success leaves: a live
#: process, its pid recorded where launcher._record_engine_pid records one,
#: and a .job.lock naming that pid the way state.RunLock.__enter__ writes it.
#: The background process detaches its fds so it cannot hold the harness's
#: stdout pipe open (a stub that does would hang subprocess.run for its whole
#: lifetime and turn every leg into a timeout).
_SUCCEEDING_LAUNCHER = """_dir=""
    _prev=""
    for _a in "$@"; do
      if [ "$_prev" = "--run-dir" ]; then _dir="$_a"; fi
      _prev="$_a"
    done
    _epid=""
    if [ -n "$_dir" ]; then
      sleep 20 >/dev/null 2>&1 </dev/null &
      _epid=$!
      printf '%s\\n' "$_epid" > "$_dir/.engine.pid"
      printf '%s stub-engine\\n' "$_epid" > "$_dir/.job.lock"
    fi
    echo "launcher: dispatched (stub) pid ${_epid:-none}"
    exit 0"""

#: A launcher stub that exits 0 and leaves NOTHING running -- the exact shape
#: of the 2026-09-06 defect (launcher.dispatch returns 0 on a successful
#: Popen; the forked engine died on EXIT_MANIFEST_MISMATCH about a second
#: later). Pre-F3 this counted as a launch.
_DEAD_ENGINE_LAUNCHER = 'echo "launcher: dispatched (stub, engine dies immediately)"\n    exit 0'


def _extract_launch_verify_helpers(src: str) -> str:
    m = _HELPERS_RE.search(src)
    assert m, (
        "could not find the POLLER-LAUNCH-VERIFY block in the poll script -- "
        "the walk-loop body calls file_mtime/verify_engine_running/"
        "engine_stderr_tail/ledger_sha256 and this harness must run the "
        "SHIPPED definitions, never a stand-in."
    )
    return m.group("block").rstrip("\n")


def _extract_walk_body(src: str) -> str:
    m = _WALK_RE.search(src)
    assert m, (
        "could not find the poller's `while ... done < <(find ...)` walk loop "
        "-- has its shape changed?"
    )
    return m.group("body").rstrip("\n")


def _make_parked_run(runs_root: Path, name: str, terminal: str = "") -> Path:
    """A run dir in the poller's RESUME condition: completed intake ledger,
    a state.json that is NOT terminal and names no live pid.

    `terminal="BLOCKED"` makes it an F1 case instead -- a PARKED run, which
    since F1 reaches the same dispatch through the auto-resume decider. The
    accounting must be identical on both paths, which is what the F1 legs at
    the bottom of this file prove."""
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
    state = {"schema_version": 1, "job_id": "pj_test", "terminal": terminal}
    if terminal == "BLOCKED":
        state["blocked"] = {"phase": "P4-COPY",
                            "reason": "script executor failed after 3 attempts",
                            "at": "2026-09-06T10:00:00+00:00"}
    (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return run_dir


def _run_harness(body: str, tmp_path: Path, launcher_body: str,
                 pre_fix: bool = False, terminal: str = "",
                 auto_resume_rc: int = 3) -> str:
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
    stub.write_text(_STUB.replace("{real_py}", f'"{sys.executable}"')
                         .replace("{LAUNCHER_BODY}", launcher_body)
                         .replace("{AUTO_RESUME_RC}", str(auto_resume_rc)),
                    encoding="utf-8")
    stub.chmod(0o755)

    runs_root = tmp_path / "runs"
    _make_parked_run(runs_root, "alpha", terminal=terminal)
    log_file = tmp_path / "poll.log"

    harness = "\n".join([
        "set -uo pipefail",
        f'export PATH="{bindir}:$PATH"',
        "PROG=presentation-intake-poll.sh",
        f'LOG_FILE="{log_file}"',
        "log() {",
        '    echo "$(date \'+%Y-%m-%dT%H:%M:%S%z\') [$PROG] $*" >> "$LOG_FILE"',
        "}",
        # F3 settle window. The real default is 8 s and is asserted
        # statically below; the check short-circuits the instant an engine is
        # proven running, so only a FAILING dispatch pays the window and 1 s
        # is enough to exercise the same code path without 8 s per leg.
        "export PRESENTATION_LAUNCH_VERIFY_S=1",
        # The SHIPPED helper block, extracted verbatim -- not a stand-in.
        _extract_launch_verify_helpers(POLL_SCRIPT.read_text(encoding="utf-8")),
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
        "SKIPPED_REFUSED_STICKY=0",
        "LEASE_TAKEOVERS=0",
        "RUN_DIRS_SEEN=0",
        'RUN_MODE=""',
        "while IFS= read -r run_dir; do",
        body,
        'done < <(find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" 2>/dev/null)',
        'log "scan complete: $NEW_LAUNCHES launched, $REFUSED_DISPATCH '
        'refused, $SKIPPED_TERMINAL terminal"',
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
    # SKIPPED_REFUSED_STICKY (F4) joined the set when the poller learned to
    # remember an unresolvable intake ledger instead of re-refusing it every
    # five minutes. The RULE is unchanged -- every `continue` must increment
    # SOME counter -- and a new exit from the walk needs a counter of its own
    # precisely so it stays visible in the summary and the telemetry event.
    counters = ("SKIPPED_NO_INTAKE", "SKIPPED_TERMINAL", "SKIPPED_RUNNING",
                "SKIPPED_LEASE_HELD", "SKIPPED_REFUSED_STICKY",
                "REFUSED_DISPATCH", "NEW_LAUNCHES")
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
    """A launcher that exits 0 AND leaves an engine RUNNING must be counted.
    Without this leg, "0 launched" above would also be satisfied by a counter
    that can never increment -- the class of broken check the negative-result
    contract warns about.

    F3 changed what this leg has to stand up: "the launcher exited 0" is no
    longer the definition of a launch, because that is exactly what the
    2026-09-06 defect satisfied twice every five minutes while nothing ran.
    The stub therefore leaves what a real success leaves -- a live process, a
    recorded pid, a .job.lock naming it. That makes this control STRICTLY
    stronger than it was: it now fails both if the counter is nailed to zero
    AND if the running-engine proof is nailed to true."""
    body = _extract_walk_body(POLL_SCRIPT.read_text(encoding="utf-8"))
    log_text = _run_harness(body, tmp_path, _SUCCEEDING_LAUNCHER)

    assert "scan complete: 1 launched, 0 refused" in log_text, (
        "a SUCCESSFUL dispatch (rc 0, engine alive, .job.lock taken) was not "
        "counted as a launch -- the counter may be nailed to zero. Log:\n"
        + log_text
    )
    assert "LAUNCHED: engine pid" in log_text, (
        "the poller counted a launch without naming the evidence it counted "
        "-- verify_engine_running's finding must reach the log. Log:\n"
        + log_text
    )


# ---------------------------------------------------------------------------
# 5. F3 -- rc 0 with a DEAD engine is a refusal, not a launch.
# ---------------------------------------------------------------------------

def test_rc_zero_with_no_running_engine_is_refused(tmp_path):
    """The measured 2026-09-06 defect, pinned. launcher.dispatch() returns 0
    the instant subprocess.Popen() succeeds; the two engines it forked at
    13:40, 13:45 and 13:50 each died about a second later on
    EXIT_MANIFEST_MISMATCH. The summary line said "2 launched" every time.

    Here the launcher stub exits 0 and leaves NOTHING running -- no pid, no
    .job.lock. That must read as 0 launched / 1 refused. This is the leg that
    fails on pristine main, where rc 0 alone was the whole verdict."""
    body = _extract_walk_body(POLL_SCRIPT.read_text(encoding="utf-8"))
    log_text = _run_harness(body, tmp_path, _DEAD_ENGINE_LAUNCHER)

    assert "scan complete: 0 launched, 1 refused" in log_text, (
        "a dispatch that exited 0 while leaving NO running engine was counted "
        "as a launch -- that is the exact historical lie. Log:\n" + log_text
    )
    assert "no engine is RUNNING" in log_text, (
        "the poller did not say why it refused to count the launch:\n"
        + log_text
    )


# ---------------------------------------------------------------------------
# 6. F1 -- a run resumed AUTOMATICALLY is accounted exactly like one resumed
#    by a human. The bounded auto-resume added a new way to REACH the
#    dispatch; it must not add a new way to LIE about the result.
# ---------------------------------------------------------------------------

def test_auto_resumed_dispatch_that_dies_is_refused_not_launched(tmp_path):
    """The two defects meeting. F1 lets a BLOCKED run be dispatched without a
    human; F3 says a dispatch only counts when an engine is provably RUNNING.
    An auto-resumed run whose engine dies on arrival -- the manifest-pin shape
    that made this whole thing dangerous -- must be REFUSED, exactly as a
    human-triggered resume would be. If F1 had been wired ahead of the
    accounting instead of through it, the summary line would have gone back to
    counting one-second deaths as launches, only now three times a day
    without anyone typing anything."""
    body = _extract_walk_body(POLL_SCRIPT.read_text(encoding="utf-8"))
    log_text = _run_harness(body, tmp_path, _DEAD_ENGINE_LAUNCHER,
                            terminal="BLOCKED", auto_resume_rc=0)

    assert "scan complete: 0 launched, 1 refused" in log_text, (
        "an AUTO-resumed dispatch that left nothing running was counted as a "
        "launch. Log:\n" + log_text
    )
    assert "no engine is RUNNING" in log_text, log_text


def test_auto_resumed_dispatch_that_lives_is_a_launch(tmp_path):
    """POSITIVE CONTROL: the same parked run with a launcher stub that leaves
    a real running engine must count as 1 launched. Without this, the leg
    above could be passing because a BLOCKED run is never dispatched at all
    -- which is the pre-F1 behaviour, not the fix."""
    body = _extract_walk_body(POLL_SCRIPT.read_text(encoding="utf-8"))
    log_text = _run_harness(body, tmp_path, _SUCCEEDING_LAUNCHER,
                            terminal="BLOCKED", auto_resume_rc=0)

    assert "scan complete: 1 launched, 0 refused" in log_text, (
        "an authorised auto-resume that produced a live engine was not "
        "counted as a launch. Log:\n" + log_text
    )
    assert "resuming parked job" in log_text, log_text


def test_a_declined_auto_resume_is_counted_terminal_not_refused(tmp_path):
    """The accounting rule this file exists for, applied to F1's new exit: a
    run dir must never leave the walk unreported, AND a parked run left parked
    is not a REFUSAL. A refusal reads as "something went wrong this tick";
    "we decided not to resume it yet" is the ordinary, correct outcome of a
    bounded retry policy and belongs in the terminal column."""
    body = _extract_walk_body(POLL_SCRIPT.read_text(encoding="utf-8"))
    log_text = _run_harness(body, tmp_path, _SUCCEEDING_LAUNCHER,
                            terminal="BLOCKED", auto_resume_rc=3)

    assert "scan complete: 0 launched, 0 refused, 1 terminal" in log_text, (
        "a declined auto-resume was miscounted (or lost entirely) -- the "
        "tally seen == launched + refused + skips no longer closes. Log:\n"
        + log_text
    )
    assert "resuming parked job" not in log_text, log_text
