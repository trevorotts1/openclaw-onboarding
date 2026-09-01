"""FIX 37 regression: presentation-intake-poll.sh must count launches for real.

Why this exists (PRESENTATION-DEPT-FIX-SPEC.md FIX 37, bug 1): the poller
walked every run dir with `find ... | while read` -- a PIPELINE. The counter
(NEW_LAUNCHES) was incremented INSIDE the while loop, i.e. inside the pipeline
subshell, so the increment was lost when the subshell exited and the final log
line always printed "scan complete: 0 launched" no matter how many engines
were dispatched. The launch count matters: FIX 5 telemetry consumes it
(poller_scan event) and operators read it to know the poller is actually
dispatching.

The fix replaces the piped walk with process substitution
(`while ...; do ...; done < <(find ...)`): the loop body then runs in the
CURRENT shell, so NEW_LAUNCHES survives to the final log line. This test pins
that shape AND proves the counter actually counts.

Spec proof targeted: "launching 2 jobs logs '2 launched'."

Four legs, mirroring tests/test_f03_poll_resume_invocation.py:

  1. STATIC   -- the walk must be process substitution (`done < <(`), never
                 `find ... | while`; the final log line
                 `scan complete: $NEW_LAUNCHES launched` must exist; the
                 counter increments are plain assignments (increments appear
                 outside any `| while` pipeline).
  2. DYNAMIC  -- extract the counting loop body VERBATIM from the shipped
                 script and execute it (not a hand-written stand-in) inside
                 the same `while ... done < <(find ...)` wrapper, against a
                 scratch RUNS_ROOT holding 2 fake completed runs (intake
                 ledger status=complete, NO state.json -- the poller's exact
                 "new intake" condition), with `python3` stubbed to a helper
                 that only mints state.json on `--new` and never spawns an
                 engine. Assert the log says "scan complete: 2 launched".
                 NOTE IN THE COMMENT BELOW: this runs the script's own loop
                 body, not the whole script -- an end-to-end run would
                 dispatch the REAL engine (`--new` followed by `--run`, which
                 spawns engine subprocesses, Kie.ai calls, a renderer).
                 That is not unit-safe and must not run unattended.
  3. NEGATIVE CONTROL -- rebuild the SAME harness with the walk reverted to
                 the pre-fix `find ... | while` pipeline shape; the exact
                 same two runs must then log "scan complete: 0 launched",
                 proving leg 2 is non-vacuous (it catches the real bug).
  4. STATIC   -- the poller stays `set -uo pipefail` (never `set -e`).

Every leg is offline: no GHL, no network, no engine subprocess is ever
spawned (the stub python3 mints only a tiny state.json). Scratch dirs are
pytest tmp_path fixtures.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
POLL_SCRIPT = _SCRIPTS_DIR / "presentation-intake-poll.sh"

# The walk loop, both shapes. The good form closes `done < <(find ...)`; the
# anchored `done < <(find` is what makes the non-greedy body stop at the REAL
# loop close rather than at the inner bare `done` of the `2>&1 | while ...`
# log-piping inside the body.
_WALK_GOOD_RE = re.compile(
    r"while IFS= read -r run_dir;\s*do"
    r"(?P<body>.*?)"
    r"done\s*<\s*<\(find",
    re.S,
)

_LOG_LINE = "scan complete: $NEW_LAUNCHES launched"

STUB_PYTHON = """#!/usr/bin/env bash
# FIX 37 sandbox stub -- never dispatches a real engine, never touches network.
#   --ledger/--out (resolve_intake.py call): exit 0, no side effects.
#   --new --run-dir <d>: mint a minimal state.json at <d>/state.json so the
#       poller's `if [ -f "$run_dir/state.json" ]` guard passes and the
#       counter increments -- MIMICS what presentation_job.py --new really
#       does, while never spawning the engine.
#   -c ... (the engine --run spawner): exit 0.
if [ "$1" = "-c" ]; then
  exit 0
fi
case " $* " in
  *" --new "*)
    dir=""
    while [ $# -gt 0 ]; do
      if [ "$1" = "--run-dir" ]; then
        dir="$2"
        shift 2
      else
        shift
      fi
    done
    if [ -n "$dir" ]; then
      mkdir -p "$dir"
      printf '{"schema_version":1,"job_id":"pj_stub","run_dir":"%s","created_at":"2026-01-01T00:00:00+00:00","intake":{},"phases":[]}' "$dir" > "$dir/state.json"
    fi
    ;;
esac
exit 0
"""


def _extract_walk_body(src: str) -> str:
    """Return the script's real while-loop body (between `while IFS= read -r
    run_dir; do` and `done < <(find ...)`), so the dynamic legs execute the
    script's own loop logic with the script's own variable semantics rather
    than a reimplementation."""
    m = _WALK_GOOD_RE.search(src)
    assert m, (
        "could not find the poller's `while ... done < <(find ...)` walk loop "
        "in the script -- has its shape changed? The anchored close is the "
        "process-substitution form FIX 37 introduced."
    )
    return m.group("body").rstrip("\n")


def _ledger_complete() -> dict:
    """Shape a completed intake ledger the way the real deck-intake-driver
    writes one: status=complete at top level (what the poller's completeness
    check reads), presentation_type nested under entries (resolve_intake's
    shape)."""
    return {
        "status": "complete",
        "complete": True,
        "requester_chat_id": "123456789",
        "requester_channel": "telegram",
        "client_name": "Acme Corp",
        "entries": {
            "presentation_type": {"value": "from_scratch", "normalized": "from_scratch"},
        },
    }


def _make_completed_run(runs_root: Path, name: str) -> Path:
    """Create one run dir exactly as the poller finds a NEW run:
    <runs_root>/pres-<name>/working/interview/intake_ledger.json with status
    complete, and NO state.json (that is what makes the poller dispatch)."""
    run_dir = runs_root / f"pres-{name}"
    ledger_dir = run_dir / "working" / "interview"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "intake_ledger.json").write_text(
        json.dumps(_ledger_complete()), encoding="utf-8")
    assert not (run_dir / "state.json").exists()
    return run_dir


@pytest.fixture()
def stub_python3(tmp_path: Path):
    """Installs the STUB_PYTHON helper on PATH and returns its bindir."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python3"
    stub.write_text(STUB_PYTHON, encoding="utf-8")
    stub.chmod(0o755)
    return bindir


def _run_counting_harness(walk_line: str, body: str, tmp_path: Path,
                          stub_bin: Path) -> str:
    """Run the counting harness and return the poll log text.

    `walk_line` is the loop header line, one of:
        'while IFS= read -r run_dir; do'                  (good: closes
            `done < <(find ...)` after the body)
        'find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" 2>/dev/null | while IFS= read -r run_dir; do'
                                                          (pre-fix: closes
            with a bare `done` -- the pipeline subshell shape)
    """
    if "| while" in walk_line:
        close = "done"
    else:
        close = 'done < <(find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" 2>/dev/null)'
    harness = (
        "set -uo pipefail\n"
        'export PATH="' + str(stub_bin) + ':$PATH"\n'
        "PROG=presentation-intake-poll.sh\n"
        'LOG_FILE="' + str(tmp_path / "poll.log") + '"\n'
        "log() {\n"
        '    echo "$(date \'+%Y-%m-%dT%H:%M:%S%z\') [$PROG] $*" >> "$LOG_FILE"\n'
        "}\n"
        + 'RUNS_ROOT="' + str(tmp_path / "runs") + '"\n'
        # The extracted body references SCRIPTS_DIR / ENGINE_ENTRY / LAUNCHER;
        # point them at the real scripts dir -- harmless, since python3 is
        # stubbed to a no-op and never executes those files.
        + 'SCRIPTS_DIR="' + str(_SCRIPTS_DIR) + '"\n'
        + 'ENGINE_ENTRY="' + str(_SCRIPTS_DIR / "presentation_job.py") + '"\n'
        + 'LAUNCHER="' + str(_SCRIPTS_DIR / "presentation_job" / "launcher.py") + '"\n'
        "NEW_LAUNCHES=0\n"
        "SKIPPED_RUNNING=0\n"
        "SKIPPED_NO_INTAKE=0\n"
        + walk_line + "\n"
        + body + "\n"
        + close + "\n"
        'log "scan complete: $NEW_LAUNCHES launched"\n'
    )
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=str(_SCRIPTS_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"counting harness failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return (tmp_path / "poll.log").read_text(encoding="utf-8")


def test_poll_script_exists_and_is_valid_bash():
    assert POLL_SCRIPT.is_file(), f"poll script not found at {POLL_SCRIPT}"
    result = subprocess.run(
        ["bash", "-n", str(POLL_SCRIPT)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, (
        f"bash -n failed on {POLL_SCRIPT}:\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# 1. STATIC -- the walk must be process substitution; counter outside pipeline.
# ---------------------------------------------------------------------------

def test_walk_uses_process_substitution_not_pipeline():
    """The `done` closing the run-dir walk must be fed by process substitution
    (`done < <(find ...)`), NOT `find ... | while`. The pipeline form puts the
    loop body in a subshell where the NEW_LAUNCHES increment is lost at
    subshell exit -- the historical FIX 37 bug (always "0 launched")."""
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    assert "done < <(find" in src, (
        "run-dir walk is not closed with process substitution; expected "
        "`done < <(find ...)` (grep for `done < <(find` in "
        "presentation-intake-poll.sh)."
    )
    m = _WALK_GOOD_RE.search(src)
    assert m, "the walk loop `while ... done < <(find ...)` was not found"
    assert not re.search(
        r"find \"\$RUNS_ROOT\".*\|\s*while IFS= read -r run_dir", src
    ), (
        "the old `find ... | while IFS= read -r run_dir` pipeline is still "
        "present -- the counter would again be incremented inside a subshell "
        "and always log 0 launched."
    )


def test_counter_increment_is_plain_assignment():
    """NEW_LAUNCHES increments must be plain assignments in the loop body --
    never part of a `| while` pipeline (the shape that loses the count)."""
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    increments = [
        line for line in src.splitlines()
        if "NEW_LAUNCHES=$((NEW_LAUNCHES + 1))" in line
    ]
    assert increments, "no NEW_LAUNCHES=$((NEW_LAUNCHES + 1)) increment found"
    for line in increments:
        left = line.split("NEW_LAUNCHES")[0]
        assert "|" not in left and "while" not in left, (
            f"NEW_LAUNCHES increment appears to be part of a pipeline: {line!r}"
        )


def test_scan_complete_log_line_exists():
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    assert _LOG_LINE in src, (
        f"the final log line {_LOG_LINE!r} is missing from the poll script"
    )


def test_poller_keeps_set_uo_pipefail_not_e():
    src = POLL_SCRIPT.read_text(encoding="utf-8")
    assert "set -uo pipefail" in src, (
        "poller must stay `set -uo pipefail` (a single missing state.json must "
        "not abort the scan; the script documents exit 0 on a no-launch scan)"
    )
    bad = [l.strip() for l in src.splitlines() if l.strip().startswith("set -e")]
    assert not bad, f"poller uses `set -e` ({bad}) -- one bad run dir would abort the scan"


# ---------------------------------------------------------------------------
# 2. DYNAMIC -- the REAL proof: execute the script's own counting loop.
# ---------------------------------------------------------------------------

def test_two_completed_runs_log_two_launches(tmp_path, stub_python3):
    """Run the poller's OWN walk loop (body extracted VERBATIM from the
    shipped script, re-wrapped in the same `while ... done < <(find ...)`
    harness) against a scratch RUNS_ROOT with 2 completed runs and no
    state.json -- the poller's exact "new intake" condition -- and assert the
    final log line says "scan complete: 2 launched".

    NOTE (why the extracted loop, not the whole script): running
    presentation-intake-poll.sh end-to-end would resolve the real scripts dir
    and then DISPATCH THE REAL ENGINE -- `python3 "$ENGINE_ENTRY" --new`
    followed by `python3 -c ... Popen(['presentation_job.py', '--run' ...])`,
    which spawns actual engine subprocesses (agent phases, Kie.ai network
    calls, a renderer). That is not a unit test and must not run unattended.
    The harness therefore executes the EXACT counting block with the SAME
    variable semantics (NEW_LAUNCHES incremented per dispatch inside the walk
    loop, then the final log line) while `python3` is stubbed: the stub mints
    the state.json that makes the poller's own `if [ -f "$run_dir/state.json" ]`
    guard pass -- no engine, no network, no GHL can ever be reached. The only
    behavior not exercised end-to-end is the python engine calls themselves,
    which are out of scope for FIX 37 (the fix is in the SHELL loop shape)."""
    runs_root = tmp_path / "runs"
    _make_completed_run(runs_root, "alpha")
    _make_completed_run(runs_root, "bravo")

    src = POLL_SCRIPT.read_text(encoding="utf-8")
    body = _extract_walk_body(src)

    log_text = _run_counting_harness(
        "while IFS= read -r run_dir; do", body, tmp_path, stub_python3
    )
    assert "scan complete: 2 launched" in log_text, (
        "expected the final log line to count 2 launches; got:\n" + log_text
    )


# ---------------------------------------------------------------------------
# 3. NEGATIVE CONTROL -- the pre-fix pipeline form must be caught.
# ---------------------------------------------------------------------------

def test_pipeline_form_would_have_logged_zero(tmp_path, stub_python3):
    """Rebuild the SAME harness with the walk reverted to the pre-fix shape
    (`find ... | while ... done` -- the pipeline subshell) and run it against
    the same 2 completed runs. The pre-fix counter was incremented inside the
    pipeline subshell, so the final log must say "scan complete: 0 launched" --
    proving the harness is capable of failing on the real historical bug and
    leg 2 is not a vacuous pass."""
    runs_root = tmp_path / "runs"
    _make_completed_run(runs_root, "alpha")
    _make_completed_run(runs_root, "bravo")

    src = POLL_SCRIPT.read_text(encoding="utf-8")
    body = _extract_walk_body(src)

    pre_fix_header = (
        'find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" 2>/dev/null '
        "| while IFS= read -r run_dir; do"
    )
    log_text = _run_counting_harness(pre_fix_header, body, tmp_path, stub_python3)
    assert "scan complete: 0 launched" in log_text, (
        "negative control did not reproduce the historical 0-launches log on "
        "the reverted pipeline shape -- the harness above may not actually be "
        "exercising the counter semantics. Log:\n" + log_text
    )
