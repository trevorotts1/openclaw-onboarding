"""F3 + F4 regression: presentation-intake-poll.sh must tell the truth about
what it launched, and must stop re-asking questions it already has answers to.

Both fixes live in the same file and F4 changes the walk F3's accounting
counts, so they ship and are pinned together.

WHAT WAS MEASURED (operator Mac, 2026-09-06)

  F3a -- A SPAWN COUNTED AS A LAUNCH. `launcher.dispatch()` returns 0 the
      instant `subprocess.Popen()` succeeds: it has proven that the OS
      accepted a fork, nothing more. Two run dirs whose state pinned an old
      manifest sha forked an engine that died about one second later on
      EXIT_MANIFEST_MISMATCH, every five minutes, for days. Ticks at 13:40,
      13:45 and 13:50 each logged:

          scan complete: 2 launched, 0 refused

      Two one-second deaths, reported as two launches, to the only line an
      operator reads.

  F3b -- EVERY LOG LINE WRITTEN TWICE. `log()` piped through
      `tee -a "$LOG_FILE"` while presentation-intake-poll.plist.template sets
      StandardOutPath AND StandardErrorPath to the very same path install.sh
      renders as $LOG_FILE. So each line landed once from tee and once from
      launchd. That is not cosmetic: the same outage was counted OFF THIS LOG
      as 5,948 consecutive AF-NOTIFY-UNCONFIGURED refusals when the true
      figure was ~2,978. A doubled log doubles every measurement taken from
      it, and the wrong number is reported with full confidence.

  F4a -- THE PARK SHELF WAS WALKED. `find "$RUNS_ROOT" -maxdepth 2 -type d
      -name "pres-*"` reaches $RUNS_ROOT/_parked/pres-<slug>. The shelf is
      exactly the place whose contents must never be dispatched again.

  F4b -- ABANDONED WAS NOT TERMINAL. The department has three terminal values
      and supervisor.py has skipped all three since it was written
      ("DONE", "BLOCKED", "ABANDONED"); the poller knew two. A run a human
      had explicitly retired was a resume candidate every five minutes.

  F4c -- REFUSALS WERE NEVER REMEMBERED. A ledger that does not resolve to a
      legal presentation_type (AF-DECK-TYPE-UNKNOWN) was re-resolved every
      tick forever -- three dirs have been failing that way since
      2026-08-07 -- each contributing a fresh "refused" to a summary line
      that is supposed to read as news.

DISCIPLINE. Every dynamic leg executes the SHIPPED script's own text -- the
walk-loop body, the launch-verify helper block, and the real `find` line --
extracted by regex, never a reimplementation. Every "must not" leg is paired
with a control proving the same harness CAN produce the other answer, because
a check that cannot fail proves nothing.

Offline by construction: `python3` is replaced by a shim that runs the REAL
interpreter for the poller's JSON probes (so terminal/pid/ledger reads are
genuine) and intercepts only the two calls that would start something -- the
engine spawner and the launcher module. No engine, no renderer, no network,
no Kie.ai. Scratch dirs are pytest tmp_path fixtures; the only processes
created are detached `sleep`s that stand in for a live engine.
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

_WALK_RE = re.compile(
    r"while IFS= read -r run_dir;\s*do(?P<body>.*?)done\s*<\s*<\((?P<find>find[^\n]*?)\)\s*\n",
    re.S,
)
_HELPERS_RE = re.compile(
    r"# >>> POLLER-LAUNCH-VERIFY-BEGIN\n(?P<block>.*?)# <<< POLLER-LAUNCH-VERIFY-END",
    re.S,
)
_LOG_FN_RE = re.compile(r"^log\(\) \{\n(?P<body>.*?)^\}\n", re.S | re.M)


def _src() -> str:
    return POLL_SCRIPT.read_text(encoding="utf-8")


def _walk_match():
    m = _WALK_RE.search(_src())
    assert m, (
        "could not find the poller's `while ... done < <(find ...)` walk loop "
        "-- has its shape changed?"
    )
    return m


def _walk_body() -> str:
    return _walk_match().group("body").rstrip("\n")


def _find_command() -> str:
    """The REAL find invocation the poller feeds its walk from."""
    return _walk_match().group("find").strip()


def _helpers() -> str:
    m = _HELPERS_RE.search(_src())
    assert m, (
        "could not find the POLLER-LAUNCH-VERIFY block -- the walk body calls "
        "file_mtime/verify_engine_running/engine_stderr_tail/ledger_sha256 "
        "and these legs must run the SHIPPED definitions, not a stand-in."
    )
    return m.group("block").rstrip("\n")


def _log_function() -> str:
    m = _LOG_FN_RE.search(_src())
    assert m, "could not find the poller's log() definition"
    return m.group(0)


# ---------------------------------------------------------------------------
# The python3 shim: real interpreter for reads, intercepted for launches.
# ---------------------------------------------------------------------------
#
# The poller calls python3 for four different things. Only two of them can
# start anything, and those two are the only ones stubbed:
#
#   REAL  `-c '<json probe>'`      -- ledger completeness, terminal, engine_pid
#   REAL  resolve_intake.py        -- the actual deck-type resolver
#   STUB  `-c '<...subprocess...>'` -- the engine --run spawner
#   STUB  `-m presentation_job.*`   -- launcher / launch_plan / env_store
#   STUB  `presentation_job.py --new` -- engine job creation
#
# Running the genuine interpreter for the probes is what lets these legs
# assert on ABANDONED and on a real unresolvable ledger instead of on a
# hand-written stand-in's idea of them. `--new` is intercepted
# UNCONDITIONALLY -- it is invoked by absolute path, so it would otherwise
# fall through to the real interpreter and run the real engine's cmd_new;
# nothing in this file wants that, and a test that can start engine code by
# accident is not offline.
_SHIM = """#!/usr/bin/env bash
REAL_PY={real_py}
_run_dir_from_argv() {
  _dir=""
  _prev=""
  for _a in "$@"; do
    if [ "$_prev" = "--run-dir" ]; then _dir="$_a"; fi
    _prev="$_a"
  done
}
if [ "$1" = "-c" ]; then
  case "$2" in
    *subprocess*)
      # The engine --run spawner. {SPAWNER_NOTE}
      _dir="$(printf '%s\\n' "$2" | sed -n "s/.*'--run-dir', *'\\([^']*\\)'.*/\\1/p" | head -n 1)"
      {SPAWNER_BODY}
      exit {SPAWNER_RC}
      ;;
    *)
      exec "$REAL_PY" "$@"
      ;;
  esac
fi
case " $* " in
  *" -m presentation_job.launcher "*)
    _run_dir_from_argv "$@"
    {LAUNCHER_BODY}
    ;;
  *" -m presentation_job.auto_resume "*)
    # F1's decider. Its own bounds -- class, phase, cap, backoff -- are proven
    # in tests/test_auto_resume.py; here it is only a seam, because these
    # legs are about the WALK -- which run dirs the poller reaches and how it
    # accounts for them. Default {AUTO_RESUME_RC} is 3 (decided: leave it
    # parked), which is the pre-F1 behaviour and therefore what every leg
    # below that predates F1 still expects.
    _run_dir_from_argv "$@"
    echo "auto-resume [STUB] decision rc {AUTO_RESUME_RC} for $_dir"
    exit {AUTO_RESUME_RC}
    ;;
  *" --new "*)
    # What the real cmd_new leaves behind, and nothing else: a state.json,
    # which is the only thing the poller's next `if [ -f ... ]` reads.
    _run_dir_from_argv "$@"
    if [ -n "$_dir" ]; then
      mkdir -p "$_dir"
      printf '{"schema_version":1,"job_id":"pj_stub","run_dir":"%s","terminal":"","phases":[]}' "$_dir" > "$_dir/state.json"
    fi
    exit 0
    ;;
  *" -m "*)
    # launch_plan / env_store / any other module: a no-op audit record.
    exit 0
    ;;
  *)
    exec "$REAL_PY" "$@"
    ;;
esac
exit 0
"""

# A stand-in for a launch that REALLY happened: a live process, its pid where
# launcher._record_engine_pid puts one, and a .job.lock naming it the way
# state.RunLock.__enter__ writes it ("<pid> <timestamp>"). fds detached so the
# process cannot hold the harness's stdout pipe open.
_LEAVE_A_RUNNING_ENGINE = """if [ -n "$_dir" ]; then
      mkdir -p "$_dir/working/logs"
      sleep 20 >/dev/null 2>&1 </dev/null &
      _epid=$!
      printf '%s\\n' "$_epid" > "$_dir/.engine.pid"
      printf '%s stub-engine\\n' "$_epid" > "$_dir/.job.lock"
    fi"""

_ALIVE_LAUNCHER = (
    'echo "launcher: dispatched (stub)"\n    ' + _LEAVE_A_RUNNING_ENGINE
    + "\n    exit 0"
)
# rc 0 and nothing running -- the measured defect's exact shape.
_DEAD_LAUNCHER = 'echo "launcher: dispatched (stub); engine died"\n    exit 0'


def _write_shim(tmp_path: Path, *, launcher_body: str,
                spawner_body: str, spawner_rc: int = 0,
                auto_resume_rc: int = 3) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "python3"
    text = (_SHIM
            .replace("{real_py}", f'"{sys.executable}"')
            .replace("{SPAWNER_NOTE}", "stubbed: never starts a real engine.")
            .replace("{SPAWNER_BODY}", spawner_body)
            .replace("{SPAWNER_RC}", str(spawner_rc))
            .replace("{AUTO_RESUME_RC}", str(auto_resume_rc))
            .replace("{LAUNCHER_BODY}", launcher_body))
    stub.write_text(text, encoding="utf-8")
    stub.chmod(0o755)
    return bindir


def _make_run(runs_root: Path, name: str, *, ledger: dict,
              state: dict | None = None) -> Path:
    run_dir = runs_root / f"pres-{name}"
    (run_dir / "working" / "interview").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps(ledger), encoding="utf-8")
    if state is not None:
        (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return run_dir


def _ledger(ptype: str = "from_scratch") -> dict:
    return {
        "status": "complete",
        "complete": True,
        "requester_chat_id": "123456789",
        "requester_channel": "telegram",
        "client_name": "Acme Corp",
        "entries": {"presentation_type": {"value": ptype, "normalized": ptype}},
    }


def _run_walk(tmp_path: Path, runs_root: Path, bindir: Path,
              *, verify_seconds: int = 1, log_name: str = "poll.log",
              body: str | None = None, find_cmd: str | None = None) -> str:
    """Execute the SHIPPED walk-loop body, with the SHIPPED helper block and
    the SHIPPED find line, against a scratch runs root.

    `body` / `find_cmd` override those two, and ONLY the negative-control legs
    at the bottom of this file pass them -- always with a SCRATCH COPY that
    reverts one specific thing to its pre-fix shape, never with anything
    written back to the worktree."""
    body = _walk_body() if body is None else body
    find_cmd = _find_command() if find_cmd is None else find_cmd
    log_file = tmp_path / log_name
    harness = "\n".join([
        "set -uo pipefail",
        f'export PATH="{bindir}:$PATH"',
        "PROG=presentation-intake-poll.sh",
        f'LOG_FILE="{log_file}"',
        "log() {",
        '    echo "$(date \'+%Y-%m-%dT%H:%M:%S%z\') [$PROG] $*" >> "$LOG_FILE"',
        "}",
        f"export PRESENTATION_LAUNCH_VERIFY_S={verify_seconds}",
        _helpers(),
        "read_run_mode() { :; }",
        f'RUNS_ROOT="{runs_root}"',
        f'SCRIPTS_DIR="{_SCRIPTS_DIR}"',
        f'ENGINE_ENTRY="{_SCRIPTS_DIR / "presentation_job.py"}"',
        f'LAUNCHER="{_SCRIPTS_DIR / "presentation_job" / "launcher.py"}"',
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
        f"done < <({find_cmd})",
        'log "scan complete: $NEW_LAUNCHES launched, $REFUSED_DISPATCH refused,'
        ' $SKIPPED_TERMINAL terminal, $SKIPPED_REFUSED_STICKY sticky,'
        ' $RUN_DIRS_SEEN seen"',
        "",
    ])
    result = subprocess.run(["bash", "-c", harness], capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, (
        "the harness itself failed -- a harness that aborts proves nothing "
        f"(this is how a control goes vacuous).\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    return log_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# F3b -- the double write.
# ---------------------------------------------------------------------------

def test_log_writes_the_line_once_not_twice(tmp_path):
    """DYNAMIC. Reproduce what launchd does -- run the poller's REAL log()
    with the process's stdout appended to the very file log() writes, exactly
    as StandardOutPath = <LOG_PATH> = $LOG_FILE arranges -- and count the
    line. It must appear ONCE.

    On the pre-fix `| tee -a "$LOG_FILE"` form this same harness counts 2,
    which is precisely how 2,978 refusals were read off this log as 5,948."""
    log_file = tmp_path / "poll.log"
    script = "\n".join([
        "PROG=presentation-intake-poll.sh",
        f'LOG_FILE="{log_file}"',
        _log_function(),
        'log "SENTINEL-ONE-LINE"',
        "",
    ])
    # `>> log_file` on the whole bash process is launchd's StandardOutPath.
    result = subprocess.run(
        ["bash", "-c", f"{{ {script} }} >> '{log_file}' 2>&1"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    text = log_file.read_text(encoding="utf-8")
    count = text.count("SENTINEL-ONE-LINE")
    assert count == 1, (
        "the poller's log() writes each line "
        f"{count} time(s) into $LOG_FILE when the process's own stdout is "
        "appended to that same file -- which is exactly how the LaunchAgent "
        "runs it (StandardOutPath = StandardErrorPath = <LOG_PATH> = "
        "$LOG_FILE). Every count taken off this log is multiplied by "
        f"{count}.\nlog contents:\n{text}"
    )


def test_log_does_not_tee_into_its_own_log_file():
    """STATIC companion: name the shape, so a future edit that reintroduces
    the pipe is rejected with the reason rather than only the symptom."""
    fn = _log_function()
    assert "tee" not in fn, (
        "log() pipes through tee again. The LaunchAgent's StandardOutPath is "
        "the SAME file $LOG_FILE names, so tee's copy plus launchd's copy is "
        f"two lines per line. Use `>>`.\nlog() is:\n{fn}"
    )
    assert '>> "$LOG_FILE"' in fn, (
        f"log() no longer appends to $LOG_FILE at all:\n{fn}"
    )


# ---------------------------------------------------------------------------
# F3a -- a launch is a RUNNING engine.
# ---------------------------------------------------------------------------

def test_dispatch_rc_zero_with_a_dead_engine_is_not_a_launch(tmp_path):
    """THE MEASURED DEFECT. Resume branch, launcher exits 0, nothing runs."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "dead", ledger=_ledger(),
              state={"schema_version": 1, "job_id": "pj_dead", "terminal": ""})
    bindir = _write_shim(tmp_path, launcher_body=_DEAD_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir)

    assert "scan complete: 0 launched, 1 refused" in log_text, (
        "a dispatch that exited 0 while leaving NO running engine was counted "
        "as a launch -- the 2026-09-06 lie, verbatim. Log:\n" + log_text
    )
    assert "no engine is RUNNING" in log_text, (
        "the refusal carries no reason:\n" + log_text
    )
    assert "[engine-stderr]" in log_text, (
        "a refused dispatch must pull the engine's own stderr into the log; "
        "without it an operator has the verdict and none of the evidence:\n"
        + log_text
    )


def test_dispatch_rc_zero_with_a_live_engine_is_a_launch(tmp_path):
    """POSITIVE CONTROL for the leg above -- the same harness, the same run
    dir, a launcher that leaves an engine actually running. Without this, "0
    launched" would also be satisfied by a counter nailed to zero."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "live", ledger=_ledger(),
              state={"schema_version": 1, "job_id": "pj_live", "terminal": ""})
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir)

    assert "scan complete: 1 launched, 0 refused" in log_text, (
        "a dispatch that left a LIVE engine holding .job.lock was not counted "
        "-- the proof may be nailed to false. Log:\n" + log_text
    )
    assert "LAUNCHED: engine pid" in log_text, (
        "the launch was counted without naming its evidence:\n" + log_text
    )


def test_new_branch_spawner_rc_zero_with_a_dead_engine_is_not_a_launch(tmp_path):
    """The --new branch gets the same treatment: `python3 -c ... Popen(...)`
    exiting 0 is not an engine. Here the spawner mints state.json (as the real
    `--new` does) but starts nothing."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "fresh", ledger=_ledger())
    # The shim's `--new` case mints state.json (as the real cmd_new does); the
    # SPAWNER then starts nothing at all.
    bindir = _write_shim(tmp_path, launcher_body="exit 0", spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir)

    assert "scan complete: 0 launched, 1 refused" in log_text, (
        "the --new branch counted a spawner that started nothing as a launch. "
        "Log:\n" + log_text
    )


# ---------------------------------------------------------------------------
# F4a -- the park shelf.
# ---------------------------------------------------------------------------

def test_walk_does_not_descend_into_the_park_shelf(tmp_path):
    """Run the poller's REAL find command against a runs root holding one live
    run and one shelved under _parked/. Only the live one may come back.

    Control in the same assertion: the live run MUST come back, so a filter
    that simply returned nothing could not pass this leg."""
    runs_root = tmp_path / "runs"
    (runs_root / "pres-live").mkdir(parents=True)
    (runs_root / "_parked" / "pres-shelved").mkdir(parents=True)
    (runs_root / "_archive" / "pres-old").mkdir(parents=True)

    result = subprocess.run(
        ["bash", "-c", f'RUNS_ROOT="{runs_root}"; {_find_command()}'],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    found = sorted(line.strip() for line in result.stdout.splitlines()
                   if line.strip())

    assert str(runs_root / "pres-live") in found, (
        "the walk lost the LIVE run -- a filter that finds nothing is not a "
        f"filter, it is an outage. find printed:\n{found}"
    )
    shelved = [p for p in found if "/_parked/" in p or "/_archive/" in p]
    assert not shelved, (
        "the walk descended into the park shelf; these are runs a human "
        f"deliberately shelved and they must never be dispatched again:\n{shelved}"
    )


def test_parked_run_is_never_dispatched(tmp_path):
    """END TO END through the real walk: a completed, non-terminal, parked run
    must produce no dispatch at all -- not a skip decision taken after the
    fact, but a run dir the poller never even sees."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root / "_parked", "shelved", ledger=_ledger(),
              state={"schema_version": 1, "job_id": "pj_park", "terminal": ""})
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir)

    assert "scan complete: 0 launched, 0 refused, 0 terminal, 0 sticky, 0 seen" in log_text, (
        "a run under _parked/ reached the walk. Log:\n" + log_text
    )
    assert "resuming parked job" not in log_text, log_text


# ---------------------------------------------------------------------------
# F4b -- ABANDONED is terminal.
# ---------------------------------------------------------------------------

def test_abandoned_is_terminal_and_is_never_resumed(tmp_path):
    """`terminal: "ABANDONED"` is the department's retirement marker
    (supervisor.py has honoured it since it was written). The poller must skip
    it, and must skip it as TERMINAL -- not as a refusal, which would read as
    "something went wrong today" forever."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "retired", ledger=_ledger(),
              state={"schema_version": 1, "job_id": "pj_gone",
                     "terminal": "ABANDONED"})
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir)

    assert "scan complete: 0 launched, 0 refused, 1 terminal, 0 sticky, 1 seen" in log_text, (
        "an ABANDONED run was not skipped as terminal. Log:\n" + log_text
    )
    assert "resuming parked job" not in log_text, log_text


@pytest.mark.parametrize("terminal", ["DONE", "BLOCKED", "ABANDONED"])
def test_all_three_terminal_values_are_honoured(tmp_path, terminal):
    """The control that makes the leg above non-vacuous in the other
    direction: DONE and BLOCKED were already honoured, so if all three now
    behave identically the change added a value rather than breaking two."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, terminal.lower(), ledger=_ledger(),
              state={"schema_version": 1, "job_id": "pj_t", "terminal": terminal})
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir)
    assert "0 launched, 0 refused, 1 terminal" in log_text, log_text


def test_a_non_terminal_run_is_still_dispatched(tmp_path):
    """POSITIVE CONTROL for the terminal legs: an empty `terminal` must still
    reach the dispatch, so "skipped terminal" cannot be passing because the
    poller stopped dispatching anything at all."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "active", ledger=_ledger(),
              state={"schema_version": 1, "job_id": "pj_a", "terminal": ""})
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir)
    assert "0 terminal" in log_text and "1 launched" in log_text, log_text


# ---------------------------------------------------------------------------
# F4c -- a refusal is remembered until the ledger changes.
# ---------------------------------------------------------------------------

def _unresolvable_ledger() -> dict:
    """A completed ledger whose deck type resolve_intake.py cannot resolve --
    the real AF-DECK-TYPE-UNKNOWN shape, run through the REAL resolver."""
    led = _ledger()
    led["entries"]["presentation_type"] = {
        "value": "not_a_real_deck_type_xyz",
        "normalized": "not_a_real_deck_type_xyz",
    }
    return led


def test_an_unresolvable_ledger_is_refused_once_then_remembered(tmp_path):
    """Tick 1 refuses and records working/.poller-refused.json with the
    ledger's sha256. Tick 2, with the ledger untouched, must NOT re-refuse --
    it must skip on the memo, counted in its own column. Tick 3, after the
    ledger is corrected, must retry.

    Three ticks in one test on purpose: the memo's whole contract is about
    what the NEXT tick does, and about the memo clearing itself the moment the
    input changes. A memo that never cleared would be worse than no memo."""
    runs_root = tmp_path / "runs"
    run_dir = _make_run(runs_root, "badtype", ledger=_unresolvable_ledger())
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")

    tick1 = _run_walk(tmp_path, runs_root, bindir, log_name="tick1.log")
    assert "scan complete: 0 launched, 1 refused, 0 terminal, 0 sticky, 1 seen" in tick1, (
        "tick 1 did not refuse the unresolvable ledger (is the REAL "
        "resolve_intake.py running?). Log:\n" + tick1
    )
    memo = run_dir / "working" / ".poller-refused.json"
    assert memo.is_file(), (
        "no refusal memo was written, so tick 2 has nothing to remember:\n"
        + tick1
    )
    recorded = json.loads(memo.read_text(encoding="utf-8"))
    assert recorded.get("ledger_sha256"), (
        f"the memo carries no ledger sha256, so it can never expire: {recorded}"
    )
    assert recorded.get("reason"), f"the memo carries no reason: {recorded}"

    tick2 = _run_walk(tmp_path, runs_root, bindir, log_name="tick2.log")
    assert "scan complete: 0 launched, 0 refused, 0 terminal, 1 sticky, 1 seen" in tick2, (
        "tick 2 re-ran the identical failing resolve instead of remembering "
        "the answer -- this is the every-5-minutes-forever loop. Log:\n" + tick2
    )

    # Correct the ledger: the memo must clear itself and the dir retry.
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps(_ledger()), encoding="utf-8")
    tick3 = _run_walk(tmp_path, runs_root, bindir, log_name="tick3.log")
    assert "0 sticky" in tick3, (
        "the refusal memo did NOT clear when the intake ledger changed, so a "
        "human fixing the deck type cannot get the run moving again -- a "
        "worse failure than the loop it replaced. Log:\n" + tick3
    )
    assert "ledger has CHANGED" in tick3, tick3
    assert not memo.is_file(), (
        "the stale memo is still on disk after the ledger changed"
    )


def test_a_resolvable_ledger_is_never_stickied(tmp_path):
    """POSITIVE CONTROL: a ledger that resolves must leave no memo, so the
    sticky column above cannot be passing because everything is stickied."""
    runs_root = tmp_path / "runs"
    run_dir = _make_run(runs_root, "goodtype", ledger=_ledger())
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir)
    assert "0 sticky" in log_text, log_text
    assert not (run_dir / "working" / ".poller-refused.json").exists(), (
        "a run whose intake resolved cleanly was given a refusal memo:\n"
        + log_text
    )


# ---------------------------------------------------------------------------
# NEGATIVE CONTROLS -- guard the guards.
#
# Every leg above says "the poller must NOT do X". A "must not" is only worth
# reading if the same harness can be shown to produce X. Each control below
# reverts ONE thing to its pre-fix shape on a SCRATCH COPY (the worktree file
# is read, never written) and proves the identical harness then reproduces the
# measured defect. Without these, a harness that silently stopped exercising
# the dispatch path would pass every leg above for the wrong reason.
# ---------------------------------------------------------------------------

_PRE_F3_RE = re.compile(
    r"[ \t]*if verify_engine_running .*?\n(?P<ind>[ \t]*)fi\n", re.S)


def _revert_to_rc_only_accounting(body: str) -> str:
    """The pre-F3 shape: rc 0 IS the launch, no proof required."""
    reverted = _PRE_F3_RE.sub(
        lambda m: m.group("ind") + "NEW_LAUNCHES=$((NEW_LAUNCHES + 1))\n", body)
    # Only INVOCATIONS matter; the surviving comments still describe the fix
    # and must not be mistaken for it (a substring match on the bare name
    # would be satisfied by prose, which is how a control goes vacuous in the
    # other direction -- by never firing at all).
    calls = [line for line in reverted.splitlines()
             if "verify_engine_running" in line and not line.lstrip().startswith("#")]
    assert not calls, (
        "the pre-F3 rewrite did not remove the running-engine proof, so this "
        f"control would be testing the FIXED shape and pass vacuously: {calls}"
    )
    assert reverted != body
    return reverted


def test_prefix_rc_only_accounting_would_have_lied(tmp_path):
    """THE CONTROL FOR THE HEADLINE FIX. The same dead-engine launcher, the
    same run dir, the same harness -- with only the running-engine proof
    reverted -- must report "1 launched". That is the 2026-09-06 log line,
    reproduced on demand, which is what makes the leg above non-vacuous."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "dead", ledger=_ledger(),
              state={"schema_version": 1, "job_id": "pj_dead", "terminal": ""})
    bindir = _write_shim(tmp_path, launcher_body=_DEAD_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir,
                         body=_revert_to_rc_only_accounting(_walk_body()))

    assert "scan complete: 1 launched, 0 refused" in log_text, (
        "the negative control did NOT reproduce the historical lie, so the "
        "dead-engine leg above may be passing for the wrong reason (a harness "
        "that never reaches the dispatch would also report 0 launched). "
        "Log:\n" + log_text
    )


def test_prefix_find_would_have_walked_the_park_shelf(tmp_path):
    """Strip the shelf filter back off the SHIPPED find line: the parked run
    must reappear. Proves the filter is what excludes it, and not the scratch
    tree being shaped wrong."""
    runs_root = tmp_path / "runs"
    (runs_root / "pres-live").mkdir(parents=True)
    (runs_root / "_parked" / "pres-shelved").mkdir(parents=True)

    reverted = re.sub(r'\s*-not -path "\$RUNS_ROOT/_\*"', "", _find_command())
    assert "-not -path" not in reverted, (
        "the pre-F4 rewrite did not remove the shelf filter -- this control "
        f"would pass vacuously. find line is: {_find_command()!r}"
    )
    result = subprocess.run(
        ["bash", "-c", f'RUNS_ROOT="{runs_root}"; {reverted}'],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    found = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert str(runs_root / "_parked" / "pres-shelved") in found, (
        "the unfiltered find did not reach the park shelf either, so the "
        f"filtered leg above proves nothing about the filter. Found:\n{found}"
    )


def test_prefix_two_value_terminal_test_would_have_resumed_abandoned(tmp_path):
    """Revert the terminal test to the two values it knew before F4: the
    ABANDONED run must then be resumed, which is what was happening every five
    minutes to every retired run."""
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "retired", ledger=_ledger(),
              state={"schema_version": 1, "job_id": "pj_gone",
                     "terminal": "ABANDONED"})
    body = _walk_body()
    # F1 split the three values: DONE and ABANDONED are ENDINGS and skip here,
    # BLOCKED is a PARK and falls through to the auto-resume decider further
    # down. The pre-F4 shape this control reverts to is therefore the two-value
    # test as it stood BEFORE either change -- DONE and BLOCKED skip, ABANDONED
    # does not -- which is exactly the historical bug: a retired run resumed
    # every five minutes.
    reverted = body.replace(
        'if [ "$TERMINAL" = "DONE" ] || [ "$TERMINAL" = "ABANDONED" ]; then',
        'if [ "$TERMINAL" = "DONE" ] || [ "$TERMINAL" = "BLOCKED" ]; then',
    )
    assert reverted != body, (
        "could not synthesize the pre-F4 two-value terminal test -- this "
        "control would pass vacuously"
    )
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")
    log_text = _run_walk(tmp_path, runs_root, bindir, body=reverted)

    assert "resuming parked job" in log_text, (
        "the two-value terminal test did NOT resume the ABANDONED run, so the "
        "leg above may be passing because nothing is ever dispatched. Log:\n"
        + log_text
    )


def test_without_the_memo_the_same_refusal_repeats(tmp_path):
    """Delete the memo between two ticks: the second tick must refuse all over
    again. Proves it is the MEMO that stops the repetition -- not the run dir
    quietly becoming un-refusable after the first pass."""
    runs_root = tmp_path / "runs"
    run_dir = _make_run(runs_root, "badtype", ledger=_unresolvable_ledger())
    bindir = _write_shim(tmp_path, launcher_body=_ALIVE_LAUNCHER,
                         spawner_body=":")

    tick1 = _run_walk(tmp_path, runs_root, bindir, log_name="c1.log")
    assert "0 launched, 1 refused" in tick1, tick1
    (run_dir / "working" / ".poller-refused.json").unlink()

    tick2 = _run_walk(tmp_path, runs_root, bindir, log_name="c2.log")
    assert "0 launched, 1 refused" in tick2 and "0 sticky" in tick2, (
        "with the memo removed the second tick did NOT re-refuse, so the "
        "sticky leg above proves nothing about the memo. Log:\n" + tick2
    )


# ---------------------------------------------------------------------------
# Shape guards -- cheap, and they name the reason.
# ---------------------------------------------------------------------------

def test_poll_script_has_valid_bash_syntax():
    result = subprocess.run(["bash", "-n", str(POLL_SCRIPT)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, (
        f"bash -n failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_running_engine_verification_has_a_documented_rollback():
    src = _src()
    assert "PRESENTATION_LAUNCH_VERIFY:-1" in src, (
        "the running-engine proof has no documented off switch; every "
        "behaviour change in this file ships with one"
    )
    assert "PRESENTATION_LAUNCH_VERIFY_S:-8" in src, (
        "the settle window is not the documented 8 seconds by default"
    )


def test_terminal_test_names_all_three_terminal_values():
    """All three of the department's terminal values must be HANDLED -- but
    since F1 they are not handled identically. DONE and ABANDONED are endings
    and are skipped on the terminal test itself; BLOCKED is a park and is
    routed to presentation_job.auto_resume. What must never happen again is a
    value falling through unmentioned, which is how ABANDONED runs were
    re-dispatched every five minutes."""
    src = _src()
    m = re.search(r'if \[ "\$TERMINAL" = "DONE" \][^\n]*', src)
    assert m, "the terminal test is not where it was"
    assert '"ABANDONED"' in m.group(0), (
        "the poller's terminal test no longer names ABANDONED, so a run a "
        f"human retired is a resume candidate again: {m.group(0)!r}"
    )
    assert 'if [ "$TERMINAL" = "BLOCKED" ]; then' in src, (
        "BLOCKED is neither skipped on the terminal test nor routed anywhere "
        "-- a parked run would fall straight through into an unconditional "
        "dispatch, which is an unbounded auto-resume"
    )
    assert "-m presentation_job.auto_resume --run-dir" in src, (
        "the BLOCKED branch does not consult the bounded auto-resume decider; "
        "the bounds (class, phase, cap, backoff) would then exist nowhere"
    )


def test_telemetry_event_carries_the_sticky_column():
    src = _src()
    assert '"skipped_refused_sticky":%d' in src, (
        "poller_scan telemetry has no skipped_refused_sticky field, so the "
        "tally seen == launched + refused + skips no longer closes"
    )
